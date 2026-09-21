import copy
import json
import re
import shutil
import sys
from pathlib import Path

from lxml import etree

SCH_NS = "http://purl.oclc.org/dsdl/schematron"
S = "{" + SCH_NS + "}"
XS_NS = "http://www.w3.org/2001/XMLSchema"
LISTE_DESENI = re.compile(r"^\s*',(.*),'\s*$", re.S)
UBL_MAINDOC = (
    "UBL-Invoice-2.1.xsd",
    "UBL-ApplicationResponse-2.1.xsd",
    "UBL-DespatchAdvice-2.1.xsd",
    "UBL-ReceiptAdvice-2.1.xsd",
    "UBL-CreditNote-2.1.xsd",
)


def _iceri_al(root, path: Path) -> None:
    for inc in root.findall(S + "include"):
        dosya, _, parca = inc.get("href").partition("#")
        alt = etree.parse(str(path.parent / dosya))
        hedef = alt.getroot() if not parca else alt.xpath("//*[@id=$i]", i=parca)[0]
        inc.getparent().replace(inc, hedef)


def _soyutlari_ayir(root) -> dict[str, etree._Element]:
    soyutlar = {}
    for oruntu in list(root.findall(S + "pattern")):
        for kural in oruntu.findall(S + "rule"):
            if kural.get("abstract") == "true":
                soyutlar[kural.get("id")] = kural
                oruntu.remove(kural)
        if oruntu.findall(S + "rule"):
            continue
        yer = list(root).index(oruntu)
        for let in oruntu.findall(S + "let"):
            oruntu.remove(let)
            root.insert(yer, let)
            yer += 1
        root.remove(oruntu)
    return soyutlar


def _kimliklendir(soyutlar: dict[str, etree._Element], root) -> None:
    for ad, kural in soyutlar.items():
        for i, a in enumerate(kural.findall(S + "assert") + kural.findall(S + "report"), 1):
            a.set("id", f"{ad}-{i}")
    for oruntu in root.findall(S + "pattern"):
        for ki, kural in enumerate(oruntu.findall(S + "rule"), 1):
            for i, a in enumerate(kural.findall(S + "assert") + kural.findall(S + "report"), 1):
                if a.get("id") is None:
                    a.set("id", f"{oruntu.get('id')}-{ki}-{i}")


def _genislet(kural, soyutlar: dict[str, etree._Element]) -> None:
    while True:
        uzantilar = kural.findall(S + "extends")
        if not uzantilar:
            return
        for ext in uzantilar:
            kaynak = soyutlar[ext.get("rule")]
            yer = list(kural).index(ext)
            kural.remove(ext)
            for cocuk in kaynak:
                kural.insert(yer, copy.deepcopy(cocuk))
                yer += 1


def _serbest_kurallari_topla(root) -> None:
    serbest = root.findall(S + "rule")
    if not serbest:
        return
    oruntu = etree.Element(S + "pattern", id="genel")
    root.insert(list(root).index(serbest[0]), oruntu)
    for kural in serbest:
        root.remove(kural)
        oruntu.append(kural)


TARIH_KORUMASI = "not(. castable as xs:date) or "
TARIH_MESAJI = "Geçersiz tarih değeri : '"


def _tarihleri_koru(root) -> None:
    for kural in root.iter(S + "rule"):
        tarihli = [a for a in kural.findall(S + "assert") if "xs:date(.)" in (a.get("test") or "")]
        if not tarihli:
            continue
        for a in tarihli:
            a.set("test", TARIH_KORUMASI + "(" + a.get("test") + ")")
        koruyucu = etree.SubElement(
            kural, S + "assert", test=". castable as xs:date", id="TarihBicimi-1"
        )
        koruyucu.text = TARIH_MESAJI
        deger = etree.SubElement(koruyucu, S + "value-of", select=".")
        deger.tail = "'. Tarih YYYY-AA-GG biçiminde geçerli bir gün olmalıdır."
        kural.insert(0, koruyucu)


def duzlestir(ana_sematron: Path) -> bytes:
    agac = etree.parse(str(ana_sematron))
    root = agac.getroot()
    _iceri_al(root, ana_sematron)
    _serbest_kurallari_topla(root)
    soyutlar = _soyutlari_ayir(root)
    _kimliklendir(soyutlar, root)
    for kural in root.iter(S + "rule"):
        _genislet(kural, soyutlar)
    _tarihleri_koru(root)
    if not any(n.get("prefix") == "xs" for n in root.findall(S + "ns")):
        ilk = root.find(S + "ns")
        root.insert(list(root).index(ilk), etree.Element(S + "ns", prefix="xs", uri=XS_NS))
    root.set("queryBinding", "xslt2")
    return etree.tostring(agac, xml_declaration=True, encoding="UTF-8")


def kod_listeleri(sch: bytes) -> dict[str, list[str]]:
    root = etree.fromstring(sch)
    listeler = {}
    for let in root.findall(S + "let"):
        eslesme = LISTE_DESENI.match(let.get("value") or "")
        if eslesme:
            listeler[let.get("name")] = [
                p.strip() for p in eslesme.group(1).split(",") if p.strip()
            ]
    return listeler


SCHXSLT_NS = "http://dmaus.name/ns/2023/schxslt"
SCHXSLT_KAPALI = ("terminate-validation-on-error", "report-fired-rule", "report-active-pattern")


def cevir(sch: bytes, transpile_xsl: Path) -> str:
    from saxonche import PySaxonProcessor

    with PySaxonProcessor(license=False) as proc:
        xp = proc.new_xslt30_processor()
        for ad in SCHXSLT_KAPALI:
            xp.set_parameter("{" + SCHXSLT_NS + "}" + ad, proc.make_boolean_value(False))
        donusum = xp.compile_stylesheet(stylesheet_file=str(transpile_xsl))
        kaynak = proc.parse_xml(xml_text=sch.decode("utf-8"))
        xsl = donusum.transform_to_string(xdm_node=kaynak)
    return xsl.replace('version="3.0"', 'version="1.0"', 1)


def _xsd_kopyala(kaynak: Path, ekler: Path) -> None:
    ubl = kaynak / "UBL-TR1.2.1_Paketi/UBLTR_1.2.1_Paketi/xsdrt"
    efatura = kaynak / "e-FaturaPaketi/e-FaturaPaketi/xsd"
    hedef = ekler / "xsd"
    shutil.rmtree(hedef, ignore_errors=True)
    shutil.copytree(ubl / "common", hedef / "common")
    (hedef / "maindoc").mkdir()
    for ad in UBL_MAINDOC:
        shutil.copy(ubl / "maindoc" / ad, hedef / "maindoc" / ad)
    shutil.copytree(efatura / "Envelope", hedef / "zarf")
    shutil.copytree(efatura / "HRXML", hedef / "HRXML")
    paket = hedef / "zarf" / "Package_1_2.xsd"
    metin = paket.read_text(encoding="utf-8")
    for ad in UBL_MAINDOC:
        metin = metin.replace(f'schemaLocation="{ad}"', f'schemaLocation="../maindoc/{ad}"')
    paket.write_text(metin, encoding="utf-8", newline="\n")
    for gereksiz in ("Package.xsd", "PackageProxy.xsd"):
        (hedef / "zarf" / gereksiz).unlink(missing_ok=True)


def uret(kaynak: Path, ekler: Path) -> dict[str, int]:
    ana = kaynak / "e-FaturaPaketi/e-FaturaPaketi/schematron/UBL-TR_Main_Schematron.xml"
    transpile = next((kaynak / "schxslt2").rglob("transpile.xsl"))
    sch = duzlestir(ana)
    xsl = cevir(sch, transpile)
    sematron = ekler / "sematron"
    sematron.mkdir(parents=True, exist_ok=True)
    (sematron / "efatura.sch").write_bytes(sch)
    (sematron / "efatura.xsl").write_text(xsl, encoding="utf-8", newline="\n")
    listeler = kod_listeleri(sch)
    kodlar = {"kaynak": "GİB e-Fatura Paketi şematronu, UBL-TR_Codelist.xml", "listeler": listeler}
    (ekler / "kodlar.json").write_text(
        json.dumps(kodlar, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n"
    )
    _xsd_kopyala(kaynak, ekler)
    root = etree.fromstring(sch)
    return {
        "kural": len(root.findall(".//" + S + "rule")),
        "assert": len(root.findall(".//" + S + "assert")),
        "liste": len(listeler),
        "xsl_bayt": len(xsl),
    }


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    kaynak = Path(args[0] if args else "kaynak")
    ekler = Path(args[1]) if len(args) > 1 else Path(__file__).parent / "ekler"
    for k, v in uret(kaynak, ekler).items():
        print(f"{k}: {v}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
