from pathlib import Path

import pytest

from efatura_kontrol import derle

KAYNAK = Path(__file__).resolve().parent.parent / "kaynak"
EKLER = Path(derle.__file__).parent / "ekler"
ANA = KAYNAK / "e-FaturaPaketi/e-FaturaPaketi/schematron/UBL-TR_Main_Schematron.xml"

paket_gerekli = pytest.mark.skipif(
    not ANA.exists(), reason="GİB paketi indirilmemiş (araclar/paket_indir.py)"
)


def test_kod_listeleri_sematrondan_okunur():
    sch = (EKLER / "sematron/efatura.sch").read_bytes()
    listeler = derle.kod_listeleri(sch)
    assert listeler["ProfileIDTypeEarchive"] == ["EARSIVFATURA"]
    assert "C62" in listeler["UnitCodeList"] and len(listeler) >= 40


def test_duzlestirilmis_sematron_yapisi():
    from lxml import etree

    root = etree.parse(str(EKLER / "sematron/efatura.sch")).getroot()
    S = derle.S
    assert root.get("queryBinding") == "xslt2"
    assert root.findall(S + "include") == [] and root.findall(S + "rule") == []
    assert not root.xpath(".//*[@abstract='true']") and root.findall(".//" + S + "extends") == []
    assert any(n.get("prefix") == "xs" for n in root.findall(S + "ns"))
    assert {p.get("id") for p in root.findall(S + "pattern")} >= {
        "genel",
        "invoice",
        "despatchadvice",
        "document",
    }
    kimlikler = [a.get("id") for a in root.iter(S + "assert")]
    assert all(kimlikler) and "TarihBicimi-1" in kimlikler and "InvoiceIDCheck-1" in kimlikler
    xsl = (EKLER / "sematron/efatura.xsl").read_text(encoding="utf-8")
    assert 'version="1.0"' in xsl[:3000] and "failed with a dynamic error" not in xsl


@paket_gerekli
def test_ekler_gib_paketiyle_guncel():
    assert derle.duzlestir(ANA) == (EKLER / "sematron/efatura.sch").read_bytes()


@paket_gerekli
def test_xsl_deterministik(tmp_path):
    sch = derle.duzlestir(ANA)
    transpile = next((KAYNAK / "schxslt2").rglob("transpile.xsl"))
    assert derle.cevir(sch, transpile) == (EKLER / "sematron/efatura.xsl").read_text(
        encoding="utf-8"
    )
