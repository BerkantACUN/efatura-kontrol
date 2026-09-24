"""Şematron açıklama kapsamı ve kuralların tetiklenme sıklığı.

    uv run python araclar/sematron_kapsam.py [--json]

1. `ekler/sematron/efatura.sch` içindeki her assert kimliğini (sch-<id>) listeler; hangisinin
   `ekler/aciklamalar.json`'da Türkçe açıklaması olduğunu sayar.
2. Sıklık için mutasyon taraması yapar: `ornekler/` altındaki geçerli belgelerden (temel
   e-Fatura, e-Arşiv, tevkifatlı fatura, e-İrsaliye) her elemanı tek tek siler, her yaprak
   elemanın metnini ve her niteliğin değerini bozar, sonucu doğrular ve hangi kuralların tetiklendiğini sayar. Sayı, bir
   kuralın "tipik bir belgede bir alan eksik ya da yanlış olduğunda" ne kadar sık devreye
   girdiğinin ölçüsüdür; GİB'e giden gerçek trafiğin istatistiği değildir.
"""

from __future__ import annotations

import argparse
import collections
import copy
import json
import sys
from pathlib import Path

from lxml import etree

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK / "src"))

from efatura_kontrol import sematron  # noqa: E402
from efatura_kontrol.belge import BelgeHatasi, yukle  # noqa: E402
from efatura_kontrol.kod import _aciklamalar  # noqa: E402

SCH = KOK / "src/efatura_kontrol/ekler/sematron/efatura.sch"
NS = {"sch": "http://purl.oclc.org/dsdl/schematron"}
BOZUK = "X?9"


def kurallar() -> dict[str, dict[str, str]]:
    """sch-<id> → {context, test, mesaj} (aynı kimlik birden çok yerde geçiyorsa ilki)."""
    agac = etree.parse(str(SCH))
    sonuc: dict[str, dict[str, str]] = {}
    for a in agac.xpath("//sch:assert|//sch:report", namespaces=NS):
        kod = f"sch-{a.get('id')}"
        if kod not in sonuc:
            sonuc[kod] = {
                "context": a.getparent().get("context", ""),
                "test": a.get("test", ""),
                "mesaj": " ".join("".join(a.itertext()).split()),
            }
    return sonuc


def _tohumlar() -> list[tuple[str, bytes]]:
    return [
        (p.name, p.read_bytes())
        for p in sorted((KOK / "ornekler").glob("*.xml"))
        if not p.name.startswith("hatali")
    ]


def _mutasyonlar(veri: bytes):
    kok = etree.fromstring(veri)
    sayi = sum(1 for e in kok.iter() if isinstance(e.tag, str))
    for sira in range(1, sayi):
        for islem in ("sil", "metin", "nitelik"):
            k = copy.deepcopy(kok)
            e = [x for x in k.iter() if isinstance(x.tag, str)][sira]
            if islem == "sil":
                e.getparent().remove(e)
            elif islem == "metin":
                if len(e) or not (e.text or "").strip():
                    continue
                e.text = BOZUK
            else:
                if not e.attrib:
                    continue
                for ad in list(e.attrib):
                    if not ad.startswith("{"):
                        e.set(ad, BOZUK)
            yield etree.tostring(k, xml_declaration=True, encoding="UTF-8")


def siklik() -> tuple[collections.Counter, int]:
    sayac: collections.Counter = collections.Counter()
    toplam = 0
    for _, veri in _tohumlar():
        for m in _mutasyonlar(veri):
            try:
                belge = yukle(m, "<mutasyon>")
            except BelgeHatasi:
                continue
            toplam += 1
            for kod in {b.kod for b in sematron.dogrula(belge) if b.seviye == "hata"}:
                sayac[kod] += 1
    return sayac, toplam


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--json", action="store_true")
    a = p.parse_args(argv)
    tum = kurallar()
    aciklamali = {k for k in _aciklamalar() if k in tum}
    sayac, toplam = siklik()
    satirlar = [
        {"kod": k, "tetiklenme": sayac.get(k, 0), "aciklamali": k in aciklamali, **tum[k]}
        for k in sorted(tum, key=lambda k: (-sayac.get(k, 0), k))
    ]
    tetiklenen = [s for s in satirlar if s["tetiklenme"]]
    ozet = {
        "kural": len(tum),
        "aciklamali": len(aciklamali),
        "kapsam": round(100 * len(aciklamali) / len(tum), 1),
        "mutasyon": toplam,
        "tetiklenen_kural": len(tetiklenen),
        "tetiklenen_aciklamali": sum(s["aciklamali"] for s in tetiklenen),
        "tetiklenme_agirlikli_kapsam": round(
            100
            * sum(s["tetiklenme"] for s in tetiklenen if s["aciklamali"])
            / max(1, sum(s["tetiklenme"] for s in tetiklenen)),
            1,
        ),
    }
    if a.json:
        print(json.dumps({"ozet": ozet, "kurallar": satirlar}, ensure_ascii=False, indent=2))
        return 0
    print(json.dumps(ozet, ensure_ascii=False))
    for s in satirlar:
        if not s["aciklamali"]:
            print(f"{s['tetiklenme']:5d}  {s['kod']}  {s['mesaj'][:110]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
