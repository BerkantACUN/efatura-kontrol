from __future__ import annotations

import json
from functools import cache
from importlib import resources
from typing import Any


@cache
def _yukle(ad: str) -> dict[str, Any]:
    return json.loads(
        resources.files("efatura_kontrol.ekler").joinpath(ad).read_text(encoding="utf-8")
    )


def listeler() -> dict[str, list[str]]:
    return _yukle("kodlar.json")["listeler"]


def liste_adlari() -> dict[str, str]:
    adlar = _yukle("aciklamalar.json")["listeler"]
    return {ad: adlar.get(ad, ad) for ad in listeler()}


def liste(ad: str, ara: str | None = None) -> dict[str, Any]:
    tum = listeler()
    if ad not in tum:
        eslesen = [k for k in tum if ad.lower() in k.lower()]
        if len(eslesen) != 1:
            raise KeyError(f"Liste bulunamadı: {ad}; adaylar: {', '.join(eslesen or tum)}")
        ad = eslesen[0]
    degerler = tum[ad]
    if ara:
        a = ara.lower()
        degerler = [d for d in degerler if a in d.lower()]
    return {
        "liste": ad,
        "aciklama": liste_adlari().get(ad, ad),
        "sayi": len(degerler),
        "degerler": degerler,
    }


def gecerli_mi(ad: str, deger: str) -> bool:
    return deger in listeler().get(ad, ())


@cache
def _aciklamalar() -> dict[str, dict[str, str]]:
    return _yukle("aciklamalar.json")["kodlar"]


def acikla(kod: str) -> dict[str, str] | None:
    a = _aciklamalar()
    if kod in a:
        return a[kod]
    if kod.startswith("xsd-"):
        return a["xsd"]
    return None
