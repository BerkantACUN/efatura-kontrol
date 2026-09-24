import json
import random
import re
from decimal import Decimal

import pytest
from pydantic import ValidationError

from efatura_kontrol import cli, mcp_server
from efatura_kontrol.kontrol import kontrol_et, ozet
from efatura_kontrol.uret import ornek_fatura

SATICI = mcp_server.ORNEK_SATICI
ALICI_TCKN = mcp_server.ORNEK_ALICI
ALICI_VKN = {
    "vkn_tckn": "1234567890",
    "unvan": "BBB Ltd. Şti.",
    "vergi_dairesi": "Kavaklıdere",
    "adres": "Atatürk Bulvarı No:1",
    "ilce": "Çankaya",
    "sehir": "Ankara",
}


def _temiz(xml: str, beklenen_tur: str = "fatura"):
    rapor = kontrol_et(xml.encode("utf-8"), None, "<test>")
    sorunlar = [(b.seviye, b.kod, b.mesaj) for b in rapor.bulgular if b.seviye != "bilgi"]
    assert sorunlar == [], sorunlar
    assert [b.kod for b in rapor.bulgular] == ["imza-yok"]
    assert rapor.sozluk()["ozet"]["tur"] == beklenen_tur
    return rapor


@pytest.mark.parametrize("senaryo", ["TEMELFATURA", "TICARIFATURA", "EARSIVFATURA"])
@pytest.mark.parametrize("alici", [ALICI_TCKN, ALICI_VKN], ids=["tckn", "vkn"])
def test_uretilen_fatura_hatasiz(senaryo, alici):
    xml = ornek_fatura(
        {
            "satici": SATICI,
            "alici": alici,
            "senaryo": senaryo,
            "no": "ABC2026000000123",
            "tarih": "2026-09-24",
            "notlar": ["Örnek not"],
            "satirlar": [
                {"ad": "Danışmanlık", "miktar": "3", "birim": "HUR", "birim_fiyat": "333.33"},
                {"ad": "Kitap", "miktar": "2", "birim_fiyat": "45.55", "kdv_orani": "10"},
                {
                    "ad": "Ekmek",
                    "miktar": "1.5",
                    "birim": "KGM",
                    "birim_fiyat": "7",
                    "kdv_orani": "1",
                },
            ],
        }
    )
    _temiz(xml, "earsiv" if senaryo == "EARSIVFATURA" else "fatura")
    o = ozet(xml.encode("utf-8"))
    assert (o["senaryo"], o["tip"], o["no"], o["satirSayisi"]) == (
        senaryo,
        "SATIS",
        "ABC2026000000123",
        3,
    )
    assert {v["yuzde"] for v in o["vergiler"]} == {"1", "10", "20"}


def test_rastgele_girdilerde_aritmetik_tutarli():
    rnd = random.Random(20260924)
    for _ in range(25):
        satirlar = [
            {
                "ad": f"Kalem {i}",
                "miktar": str(Decimal(rnd.randint(1, 99999)) / rnd.choice([1, 10, 100, 1000])),
                "birim": rnd.choice(["C62", "KGM", "LTR", "MTR", "HUR"]),
                "birim_fiyat": str(Decimal(rnd.randint(0, 10**7)) / rnd.choice([1, 100, 10000])),
                "kdv_orani": rnd.choice(["1", "8", "10", "18", "20"]),
            }
            for i in range(rnd.randint(1, 12))
        ]
        _temiz(ornek_fatura({"satici": SATICI, "alici": ALICI_VKN, "satirlar": satirlar}))


@pytest.mark.parametrize(
    ("degisiklik", "parca"),
    [
        ({"satici": {**SATICI, "vkn_tckn": "123"}}, "10 (VKN) ya da 11 (TCKN)"),
        ({"satici": {**SATICI, "unvan": None}}, "unvan zorunlu"),
        ({"alici": {**ALICI_TCKN, "soyad": None}}, "ad ve soyad zorunlu"),
        ({"satirlar": [{"ad": "x", "miktar": "1", "birim": "ADET", "birim_fiyat": "1"}]}, "C62"),
        ({"satirlar": [{"ad": "x", "miktar": "1", "birim_fiyat": "1", "kdv_orani": "0"}]}, "0"),
        ({"satirlar": []}, "satirlar"),
        (
            {
                "satirlar": [{"ad": "x", "miktar": "1", "birim_fiyat": "1", "kdv_orani": "20"}]
                * 1001
            },
            "1000",
        ),
        ({"senaryo": "IHRACAT"}, "senaryo"),
    ],
)
def test_gecersiz_girdi_reddedilir(degisiklik, parca):
    veri = {"satici": SATICI, "alici": ALICI_TCKN, "satirlar": [mcp_server.ORNEK_SATIR]}
    with pytest.raises(ValidationError, match=re.escape(parca)):
        ornek_fatura({**veri, **degisiklik})


def test_mcp_ornek_fatura():
    sonuc = mcp_server.ornek_fatura(
        satici=SATICI, alici=ALICI_TCKN, satirlar=[mcp_server.ORNEK_SATIR], tarih="2026-01-02"
    )
    assert sonuc["ozet"]["gecerli"] is True and sonuc["ozet"]["hata"] == 0
    assert [b["kod"] for b in sonuc["bulgular"]] == ["imza-yok"]
    assert "<cbc:IssueDate>2026-01-02</cbc:IssueDate>" in sonuc["xml"]


def test_cli_ornek_fatura(tmp_path, capsys, monkeypatch):
    assert cli.main(["ornek-fatura"]) == 0
    cikti = capsys.readouterr()
    assert cikti.out.startswith("<?xml") and "GEÇERLİ" in cikti.err

    girdi = tmp_path / "girdi.json"
    girdi.write_text(
        json.dumps({"satici": SATICI, "alici": ALICI_VKN, "satirlar": [mcp_server.ORNEK_SATIR]}),
        encoding="utf-8",
    )
    hedef = tmp_path / "f.xml"
    assert (
        cli.main(["ornek-fatura", str(girdi), "-o", str(hedef), "--senaryo", "EARSIVFATURA"]) == 0
    )
    _temiz(hedef.read_text(encoding="utf-8"), "earsiv")
    assert cli.main(["dogrula", str(hedef), "--sessiz"]) == 0

    bozuk = tmp_path / "bozuk.json"
    bozuk.write_text('{"satici": {"vkn_tckn": "1"}}', encoding="utf-8")
    assert cli.main(["ornek-fatura", str(bozuk)]) == 2
    assert "girdi geçersiz" in capsys.readouterr().err
    assert cli.main(["ornek-fatura", str(tmp_path / "yok.json")]) == 2
