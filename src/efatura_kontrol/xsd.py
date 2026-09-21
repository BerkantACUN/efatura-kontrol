from __future__ import annotations

from functools import cache
from importlib import resources

from lxml import etree

from efatura_kontrol.belge import Belge
from efatura_kontrol.bulgu import Bulgu

DOSYALAR = {
    "fatura": "xsd/maindoc/UBL-Invoice-2.1.xsd",
    "earsiv": "xsd/maindoc/UBL-Invoice-2.1.xsd",
    "irsaliye": "xsd/maindoc/UBL-DespatchAdvice-2.1.xsd",
    "irsaliye-yaniti": "xsd/maindoc/UBL-ReceiptAdvice-2.1.xsd",
    "uygulama-yaniti": "xsd/maindoc/UBL-ApplicationResponse-2.1.xsd",
    "zarf": "xsd/zarf/PackageProxy_1_2.xsd",
}


@cache
def sema(tur: str) -> etree.XMLSchema:
    yol = resources.files("efatura_kontrol.ekler").joinpath(DOSYALAR[tur])
    with resources.as_file(yol) as dosya:
        return etree.XMLSchema(file=str(dosya))


def _kod(hata: etree._LogEntry) -> str:
    ad = hata.type_name.lower().removeprefix("schemav_").replace("_", "-")
    return f"xsd-{ad}"


def dogrula(belge: Belge) -> list[Bulgu]:
    s = sema(belge.tur)
    if s.validate(belge.agac):
        return []
    return [
        Bulgu(
            kod=_kod(h),
            seviye="hata",
            kaynak="xsd",
            mesaj=h.message,
            konum=h.path or None,
            satir=h.line or None,
        )
        for h in s.error_log
    ]
