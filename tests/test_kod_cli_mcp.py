import asyncio
import json
import subprocess
import sys
from pathlib import Path

import pytest

from efatura_kontrol import PAKET, SURUM, cli, kod, mcp_server
from efatura_kontrol.toplu import dosyalari_bul, toplu_kontrol
from tests.conftest import degistir


def test_kod_listeleri():
    adlar = kod.liste_adlari()
    assert "UnitCodeList" in adlar and "Birim" in adlar["UnitCodeList"]
    assert kod.gecerli_mi("UnitCodeList", "C62") and not kod.gecerli_mi("UnitCodeList", "ADET")
    assert kod.gecerli_mi("InvoiceTypeCodeList", "TEVKIFAT")
    assert kod.liste("unitcode", "KGM")["degerler"] == ["KGM"]
    assert "62750" in kod.liste("WithholdingTaxTypeWithPercent", "627")["degerler"]
    assert kod.liste("TaxType")["sayi"] > 20
    with pytest.raises(KeyError):
        kod.liste("Type")
    with pytest.raises(KeyError):
        kod.liste("yok-boyle-liste")


def test_aciklamalar_kodlarla_tutarli():
    assert kod.acikla("sch-GeneralUnitCodeCheck-1")["duzeltme"].startswith("Adet için C62")
    assert kod.acikla("xsd-cvc-complex-type-2-4-a")["baslik"].startswith("Şema")
    assert kod.acikla("olmayan-kod") is None
    aciklamalar = kod._aciklamalar()
    sch = Path("src/efatura_kontrol/ekler/sematron/efatura.sch").read_text(encoding="utf-8")
    for k in aciklamalar:
        if k.startswith("sch-") and k != "sch-degerlendirme":
            assert f'id="{k[4:]}"' in sch, k
        assert set(aciklamalar[k]) == {"baslik", "aciklama", "duzeltme"}


def test_cli_dogrula(ornekler, capsys, tmp_path):
    assert cli.main(["dogrula", str(ornekler / "temel_fatura.xml")]) == 0
    cikti = capsys.readouterr().out
    assert "GEÇERLİ" in cikti and "imza-yok" in cikti
    assert (
        cli.main(["dogrula", str(ornekler / "temel_fatura.xml"), "--tur", "earsiv", "--json"]) == 1
    )
    veri = json.loads(capsys.readouterr().out)
    assert veri["ozet"]["hata"] == 1 and veri["bulgular"][0]["kod"] == "sch-ProfileIDCheck-2"
    bozuk = tmp_path / "bozuk.xml"
    bozuk.write_bytes(
        degistir((ornekler / "temel_fatura.xml").read_bytes(), 'unitCode="KWH"', 'unitCode="ADET"')
    )
    assert cli.main(["dogrula", str(bozuk), str(ornekler / "irsaliye.xml"), "--sessiz"]) == 1
    satirlar = capsys.readouterr().out.strip().splitlines()
    assert len(satirlar) == 2 and "GEÇERSİZ" in satirlar[0] and "GEÇERLİ" in satirlar[1]


def test_cli_ozet_kod_acikla(ornekler, capsys):
    assert cli.main(["ozet", str(ornekler / "tevkifat_fatura.xml")]) == 0
    assert json.loads(capsys.readouterr().out)["tip"] == "TEVKIFAT"
    assert cli.main(["ozet", "yok.xml"]) == 1
    assert "dosya-yok" in capsys.readouterr().err
    assert cli.main(["kod"]) == 0
    assert "ProfileIDType" in json.loads(capsys.readouterr().out)
    assert cli.main(["kod", "CurrencyCodeList", "--ara", "TRY"]) == 0
    assert json.loads(capsys.readouterr().out)["degerler"] == ["TRY"]
    assert cli.main(["kod", "Type"]) == 1
    assert cli.main(["acikla", "hesap-dip-odenecek"]) == 0
    assert "tevkifat" in json.loads(capsys.readouterr().out)["aciklama"]
    assert cli.main(["acikla", "yok"]) == 1


def test_cli_toplu(ornekler, capsys, tmp_path):
    for i in range(5):
        (tmp_path / f"f{i}.xml").write_bytes((ornekler / "temel_fatura.xml").read_bytes())
    (tmp_path / "alt").mkdir()
    (tmp_path / "alt" / "kirik.xml").write_bytes(b"<Invoice")
    (tmp_path / "not.txt").write_text("x")
    assert len(dosyalari_bul([tmp_path])) == 6
    assert cli.main(["toplu", str(tmp_path), "--isci", "1"]) == 1
    cikti = capsys.readouterr().out
    assert "6 belge, 1 geçersiz" in cikti
    assert cli.main(["toplu", str(tmp_path / "f0.xml"), "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["ozet"]["gecerli"] is True
    eksik = list(toplu_kontrol([tmp_path / "yok"]))
    assert len(eksik) == 1 and eksik[0].bulgular[0].kod == "dosya-yok"
    (tmp_path / "bos_klasor").mkdir()
    assert list(toplu_kontrol([tmp_path / "bos_klasor"])) == []


def test_cli_surum_ve_derle_komutu(capsys):
    with pytest.raises(SystemExit):
        cli.main(["--version"])
    assert SURUM in capsys.readouterr().out


def test_mcp_araclari(ornekler):
    araclar = asyncio.run(mcp_server.mcp.list_tools())
    assert {a.name for a in araclar} == {
        "belge_dogrula",
        "belge_ozeti",
        "bulgu_acikla",
        "kod_listesi",
        "kod_listeleri",
        "ornek_fatura",
    }
    assert all(
        a.description and a.annotations.model_dump(by_alias=True)["readOnlyHint"] for a in araclar
    )
    sonuc = mcp_server.belge_dogrula(str(ornekler / "temel_fatura.xml"))
    assert sonuc["ozet"]["gecerli"] is True
    xml = (ornekler / "temel_fatura.xml").read_text(encoding="utf-8")
    sonuc = mcp_server.belge_dogrula(
        xml=xml.replace('unitCode="KWH"', 'unitCode="ADET"'), tur="fatura"
    )
    assert sonuc["ozet"]["hata"] == 1 and sonuc["dosya"] == "<xml>"
    assert mcp_server.belge_ozeti(xml=xml)["no"] == "GIB2026000000001"
    assert mcp_server.belge_ozeti(xml="<x")["hata"] == "xml-bicim"
    assert mcp_server.bulgu_acikla("hesap-satir")["baslik"]
    assert mcp_server.bulgu_acikla("yok")["aciklama"] is None
    assert mcp_server.kod_listesi("UnitCodeList", "C62")["degerler"] == ["C62"]
    assert "hata" in mcp_server.kod_listesi("Type")
    assert mcp_server.kod_listeleri()["paket"] == PAKET
    with pytest.raises(ValueError):
        mcp_server.belge_dogrula()


def test_mcp_sunucu_stdio_baslar():
    istek = json.dumps(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "0"},
            },
        }
    )
    p = subprocess.run(
        [sys.executable, "-m", "efatura_kontrol.cli", "mcp"],
        input=istek + "\n",
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=120,
    )
    assert '"serverInfo"' in p.stdout and "efatura-kontrol" in p.stdout


def test_argumansiz_calisinca_mcp_sunucusu_baslar(monkeypatch):
    from efatura_kontrol.cli import _komutlari_coz

    monkeypatch.setattr("sys.stdin", type("S", (), {"isatty": lambda self: False})())
    assert _komutlari_coz([]) == ["mcp"]
    assert _komutlari_coz(["ozet", "a.xml"]) == ["ozet", "a.xml"]
    monkeypatch.setattr("sys.stdin", type("S", (), {"isatty": lambda self: True})())
    assert _komutlari_coz([]) == []
    monkeypatch.setattr("sys.stdin", None)
    assert _komutlari_coz([]) == ["mcp"]


def test_argumansiz_stdio_sunucusu_gercekten_konusur():
    istek = json.dumps(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "glama-benzeri", "version": "0"},
            },
        }
    )
    p = subprocess.run(
        [sys.executable, "-m", "efatura_kontrol.cli"],
        input=istek + "\n",
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=120,
    )
    assert '"serverInfo"' in p.stdout


def test_mcp_arac_tanimlari_eksiksiz():
    araclar = asyncio.run(mcp_server.mcp.list_tools())
    for a in araclar:
        d = a.description
        for bolum in ("Ne zaman:", "Dönüş (JSON nesne)", "English:"):
            assert bolum in d, (a.name, bolum)
        assert "örne" in d.lower(), a.name
        assert a.title, a.name
        n = a.annotations.model_dump(by_alias=True)
        assert n["title"] and n["readOnlyHint"] is True and n["destructiveHint"] is False, a.name
        assert n["idempotentHint"] is True and n["openWorldHint"] is False, a.name
        sema = a.inputSchema if hasattr(a, "inputSchema") else a.input_schema
        for ad, ozellik in sema.get("properties", {}).items():
            assert ozellik.get("description") and ozellik.get("examples"), (a.name, ad)
    dogrula = next(a for a in araclar if a.name == "belge_dogrula")
    assert "uzak-dosya-kapali" in dogrula.description
