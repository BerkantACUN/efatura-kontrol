from __future__ import annotations

import os
from collections.abc import Iterable, Iterator
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from efatura_kontrol.bulgu import Rapor

UZANTILAR = frozenset({".xml"})


def dosyalari_bul(yollar: Iterable[str | Path]) -> list[Path]:
    dosyalar: list[Path] = []
    for yol in yollar:
        p = Path(yol)
        if p.is_dir():
            dosyalar.extend(sorted(x for x in p.rglob("*") if x.suffix.lower() in UZANTILAR))
        else:
            dosyalar.append(p)
    dosyalar.sort(key=lambda p: -p.stat().st_size if p.exists() else 0)
    return dosyalar


def _isci_hazirla() -> None:
    from efatura_kontrol.kontrol import hazirla

    hazirla()


def _kontrol(yol: str) -> Rapor:
    from efatura_kontrol.kontrol import kontrol_et

    return kontrol_et(yol)


def toplu_kontrol(yollar: Iterable[str | Path], isci: int | None = None) -> Iterator[Rapor]:
    dosyalar = [str(p) for p in dosyalari_bul(yollar)]
    if not dosyalar:
        return
    isci = isci or min(len(dosyalar), os.cpu_count() or 1)
    if isci <= 1 or len(dosyalar) < 4:
        _isci_hazirla()
        for yol in dosyalar:
            yield _kontrol(yol)
        return
    with ProcessPoolExecutor(max_workers=isci, initializer=_isci_hazirla) as havuz:
        yield from havuz.map(_kontrol, dosyalar, chunksize=4)
