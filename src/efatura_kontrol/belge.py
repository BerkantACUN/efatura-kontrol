from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from lxml import etree

NS = {
    "inv": "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2",
    "desp": "urn:oasis:names:specification:ubl:schema:xsd:DespatchAdvice-2",
    "recp": "urn:oasis:names:specification:ubl:schema:xsd:ReceiptAdvice-2",
    "apr": "urn:oasis:names:specification:ubl:schema:xsd:ApplicationResponse-2",
    "cac": "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2",
    "cbc": "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2",
    "ext": "urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2",
    "ds": "http://www.w3.org/2000/09/xmldsig#",
    "xades": "http://uri.etsi.org/01903/v1.3.2#",
    "sh": "http://www.unece.org/cefact/namespaces/StandardBusinessDocumentHeader",
    "ef": "http://www.efatura.gov.tr/package-namespace",
}
CBC = "{" + NS["cbc"] + "}"
CAC = "{" + NS["cac"] + "}"
KOK_TURLERI = {
    "{" + NS["inv"] + "}Invoice": "fatura",
    "{" + NS["desp"] + "}DespatchAdvice": "irsaliye",
    "{" + NS["recp"] + "}ReceiptAdvice": "irsaliye-yaniti",
    "{" + NS["apr"] + "}ApplicationResponse": "uygulama-yaniti",
    "{" + NS["sh"] + "}StandardBusinessDocument": "zarf",
}
TURLER = ("fatura", "earsiv", "irsaliye", "irsaliye-yaniti", "uygulama-yaniti", "zarf")
AZAMI_BAYT = 50 * 1024 * 1024
_PARSER = etree.XMLParser(resolve_entities=False, no_network=True, huge_tree=False)
_ZARF_ICI = etree.XPath("/sh:StandardBusinessDocument/ef:Package/*/*/*[1]", namespaces=NS)
_TIP_ETIKETLERI = (
    CBC + "InvoiceTypeCode",
    CBC + "DespatchAdviceTypeCode",
    CBC + "ReceiptAdviceTypeCode",
)
_Q_DESENI = re.compile(r"Q\{([^}]*)\}([^/\[\]@]+)")


class BelgeHatasi(Exception):
    def __init__(self, kod: str, mesaj: str, satir: int | None = None):
        super().__init__(mesaj)
        self.kod = kod
        self.mesaj = mesaj
        self.satir = satir


@dataclass(slots=True)
class Belge:
    ad: str
    veri: bytes
    agac: etree._ElementTree
    kok: etree._Element
    tur: str
    icerik: etree._Element | None
    profil: str | None
    tip: str | None

    @property
    def kodlama(self) -> str:
        return self.agac.docinfo.encoding or "utf-8"

    def metin(self) -> str:
        return self.veri.decode(self.kodlama, errors="replace")

    def satir(self, konum: str) -> int | None:
        try:
            sonuc = self.agac.xpath(svrl_konumu_cevir(konum))
        except etree.XPathError:
            return None
        if not sonuc:
            return None
        dugum = sonuc[0]
        if not isinstance(dugum, etree._Element):
            dugum = getattr(dugum, "getparent", lambda: None)()
        return getattr(dugum, "sourceline", None)


def svrl_konumu_cevir(konum: str) -> str:
    konum = _Q_DESENI.sub(
        lambda m: f"*[namespace-uri()='{m.group(1)}' and local-name()='{m.group(2)}']", konum
    )
    return konum.replace("/@*[namespace-uri()='' and local-name()=", "/@*[local-name()=")


def yukle(kaynak: str | Path | bytes, ad: str | None = None, tur: str | None = None) -> Belge:
    if isinstance(kaynak, bytes):
        veri = kaynak
        ad = ad or "<bellek>"
    else:
        yol = Path(kaynak)
        if not yol.is_file():
            raise BelgeHatasi("dosya-yok", f"Dosya bulunamadı: {yol}")
        ad = ad or yol.name
        if yol.stat().st_size > AZAMI_BAYT:
            raise BelgeHatasi(
                "xml-boyut", f"Dosya {AZAMI_BAYT // (1024 * 1024)} MB sınırını aşıyor"
            )
        veri = yol.read_bytes()
    if len(veri) > AZAMI_BAYT:
        raise BelgeHatasi("xml-boyut", f"Belge {AZAMI_BAYT // (1024 * 1024)} MB sınırını aşıyor")
    try:
        kok = etree.fromstring(veri, _PARSER)
    except etree.XMLSyntaxError as e:
        raise BelgeHatasi("xml-bicim", f"XML iyi biçimli değil: {e.msg}", e.lineno) from None
    kok_turu = KOK_TURLERI.get(kok.tag)
    if kok_turu is None:
        raise BelgeHatasi("xml-kok", f"Tanınmayan kök eleman: {kok.tag}", kok.sourceline)
    if tur is not None and tur not in TURLER:
        raise BelgeHatasi("tur-bilinmiyor", f"Bilinmeyen tür: {tur}; geçerli: {', '.join(TURLER)}")
    icerik = kok
    if kok_turu == "zarf":
        ic = _ZARF_ICI(kok)
        icerik = ic[0] if ic else None
    profil = tip = None
    if icerik is not None:
        p = icerik.find(CBC + "ProfileID")
        profil = (p.text or "").strip() or None if p is not None else None
        for etiket in _TIP_ETIKETLERI:
            t = icerik.find(etiket)
            if t is not None:
                tip = (t.text or "").strip() or None
                break
    if kok_turu == "fatura" and profil == "EARSIVFATURA":
        kok_turu = "earsiv"
    if tur == "earsiv" and kok_turu == "fatura":
        kok_turu = "earsiv"
    elif tur == "fatura" and kok_turu == "earsiv":
        kok_turu = "fatura"
    return Belge(ad, veri, kok.getroottree(), kok, kok_turu, icerik, profil, tip)
