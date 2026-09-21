from __future__ import annotations

from lxml import etree

from efatura_kontrol.belge import NS, Belge
from efatura_kontrol.bulgu import Bulgu

DS = "{" + NS["ds"] + "}"
XADES = "{" + NS["xades"] + "}"
_IMZALAR = etree.XPath(
    "ext:UBLExtensions/ext:UBLExtension/ext:ExtensionContent/ds:Signature", namespaces=NS
)
_KIMLIKLI = etree.XPath("//*[@Id=$kimlik or @ID=$kimlik or @id=$kimlik]")
_ZORUNLU = (
    (DS + "SignedInfo", "ds:SignedInfo"),
    (DS + "SignatureValue", "ds:SignatureValue"),
    (
        DS + "KeyInfo/" + DS + "X509Data/" + DS + "X509Certificate",
        "ds:KeyInfo/ds:X509Data/ds:X509Certificate",
    ),
    (DS + "Object//" + XADES + "SigningTime", "xades:SigningTime"),
    (DS + "Object//" + XADES + "SigningCertificate", "xades:SigningCertificate"),
)
IMZASIZ_TURLER = frozenset({"zarf"})


def _bulgu(kod: str, seviye: str, mesaj: str, dugum: etree._Element) -> Bulgu:
    return Bulgu(
        kod=kod,
        seviye=seviye,
        kaynak="imza",
        mesaj=mesaj,
        konum=dugum.getroottree().getpath(dugum),
        satir=dugum.sourceline,
    )


def dogrula(belge: Belge) -> list[Bulgu]:
    kok = belge.icerik
    if kok is None or belge.tur in IMZASIZ_TURLER:
        return []
    imzalar = _IMZALAR(kok)
    if not imzalar:
        return [
            _bulgu(
                "imza-yok",
                "bilgi",
                "Belge elektronik imza taşımıyor; GİB'e gönderilecek belgede XAdES imzası (ext:UBLExtensions içinde ds:Signature) bulunmalıdır, taslak için normaldir",
                kok,
            )
        ]
    bulgular: list[Bulgu] = []
    for imza in imzalar:
        for yol, ad in _ZORUNLU:
            if imza.find(yol) is None:
                bulgular.append(_bulgu("imza-yapi", "hata", f"İmzada {ad} elemanı yok", imza))
        for ref in imza.iterfind(DS + "SignedInfo/" + DS + "Reference"):
            uri = ref.get("URI") or ""
            if uri.startswith("#") and not _KIMLIKLI(kok, kimlik=uri[1:]):
                bulgular.append(
                    _bulgu(
                        "imza-referans",
                        "hata",
                        f"İmza referansı {uri} belgede bir Id ile eşleşmiyor",
                        ref,
                    )
                )
    if not bulgular:
        bulgular.append(
            _bulgu(
                "imza-var",
                "bilgi",
                f"{len(imzalar)} XAdES imzası var ve yapısı tam; kriptografik doğrulama bu araçta yapılmaz",
                imzalar[0],
            )
        )
    return bulgular
