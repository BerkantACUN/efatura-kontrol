from __future__ import annotations

from functools import cache
from importlib import resources

from lxml import etree

from efatura_kontrol.belge import Belge
from efatura_kontrol.bulgu import Bulgu

SVRL = "{http://purl.oclc.org/dsdl/svrl}"
TUR_PARAMETRESI = {
    "fatura": "efatura",
    "earsiv": "earchive",
    "irsaliye": "efatura",
    "irsaliye-yaniti": "efatura",
    "uygulama-yaniti": "efatura",
    "zarf": "efatura",
}


class Motor:
    def __init__(self) -> None:
        from saxonche import PySaxonProcessor

        self.islemci = PySaxonProcessor(license=False)
        xslt = self.islemci.new_xslt30_processor()
        yol = resources.files("efatura_kontrol.ekler").joinpath("sematron/efatura.xsl")
        with resources.as_file(yol) as dosya:
            self.calistirici = xslt.compile_stylesheet(stylesheet_file=str(dosya))
        self._parametre: str | None = None

    def svrl(self, belge: Belge) -> bytes:
        parametre = TUR_PARAMETRESI[belge.tur]
        if parametre != self._parametre:
            self.calistirici.set_parameter("type", self.islemci.make_string_value(parametre))
            self._parametre = parametre
        dugum = self.islemci.parse_xml(xml_text=belge.metin())
        return self.calistirici.transform_to_string(xdm_node=dugum).encode("utf-8")


@cache
def motor() -> Motor:
    return Motor()


def _bulgu(belge: Belge, dugum: etree._Element, seviye: str) -> Bulgu:
    metin = dugum.find(SVRL + "text")
    mesaj = " ".join("".join(metin.itertext()).split()) if metin is not None else ""
    konum = dugum.get("location")
    kural = dugum.get("id") or dugum.get("test") or ""
    return Bulgu(
        kod=f"sch-{kural}" if dugum.get("id") else "sch-kural",
        seviye=seviye,
        kaynak="sematron",
        mesaj=mesaj,
        gib_mesaj=mesaj,
        kural=dugum.get("test"),
        konum=konum,
        satir=belge.satir(konum) if konum else None,
    )


def _degerlendirme_hatasi(dugum: etree._Element) -> Bulgu:
    aciklama = " ".join("".join(dugum.itertext()).split())
    return Bulgu(
        kod="sch-degerlendirme",
        seviye="hata",
        kaynak="sematron",
        mesaj=f"GİB kuralı bu değerle değerlendirilemedi ({dugum.get('code')}): {aciklama}",
        kural=dugum.get("code"),
    )


def dogrula(belge: Belge) -> list[Bulgu]:
    rapor = etree.fromstring(motor().svrl(belge))
    bulgular = [_bulgu(belge, d, "hata") for d in rapor.iter(SVRL + "failed-assert")]
    bulgular += [_bulgu(belge, d, "uyari") for d in rapor.iter(SVRL + "successful-report")]
    bulgular += [_degerlendirme_hatasi(d) for d in rapor.iter(SVRL + "error")]
    return bulgular
