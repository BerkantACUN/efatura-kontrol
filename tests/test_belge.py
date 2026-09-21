import pytest

from efatura_kontrol import belge
from tests.conftest import degistir


def test_fatura_yuklenir_ve_taninir(temel_fatura):
    b = belge.yukle(temel_fatura, "temel.xml")
    assert (b.tur, b.profil, b.tip) == ("fatura", "TEMELFATURA", "SATIS")
    assert b.icerik is b.kok
    assert b.kodlama.lower() == "utf-8"


def test_earsiv_profilden_bulunur_ve_tur_zorlanabilir(earsiv_fatura):
    assert belge.yukle(earsiv_fatura).tur == "earsiv"
    assert belge.yukle(earsiv_fatura, tur="fatura").tur == "fatura"
    with pytest.raises(belge.BelgeHatasi) as e:
        belge.yukle(earsiv_fatura, tur="makbuz")
    assert e.value.kod == "tur-bilinmiyor"


def test_irsaliye_ve_zarf(irsaliye, temel_fatura):
    b = belge.yukle(irsaliye)
    assert (b.tur, b.profil, b.tip) == ("irsaliye", "TEMELIRSALIYE", "SEVK")
    zarf = (
        b'<sh:StandardBusinessDocument xmlns:sh="http://www.unece.org/cefact/namespaces/StandardBusinessDocumentHeader" '
        b'xmlns:ef="http://www.efatura.gov.tr/package-namespace"><sh:StandardBusinessDocumentHeader/>'
        b"<ef:Package><Elements><ElementType>INVOICE</ElementType><ElementCount>1</ElementCount><ElementList>"
        + temel_fatura.split(b"?>", 1)[1]
        + b"</ElementList></Elements></ef:Package></sh:StandardBusinessDocument>"
    )
    z = belge.yukle(zarf)
    assert z.tur == "zarf" and z.profil == "TEMELFATURA" and z.icerik is not None


def test_bozuk_xml_ve_yabanci_kok():
    with pytest.raises(belge.BelgeHatasi) as e:
        belge.yukle(b"<Invoice><cbc:ID>1</Invoice>")
    assert e.value.kod == "xml-bicim" and e.value.satir == 1
    with pytest.raises(belge.BelgeHatasi) as e:
        belge.yukle(b"<Fatura/>")
    assert e.value.kod == "xml-kok"
    with pytest.raises(belge.BelgeHatasi) as e:
        belge.yukle("yok/boyle/bir/dosya.xml")
    assert e.value.kod == "dosya-yok"


def test_boyut_siniri(monkeypatch):
    monkeypatch.setattr(belge, "AZAMI_BAYT", 10)
    with pytest.raises(belge.BelgeHatasi) as e:
        belge.yukle(b"<Invoice xmlns='urn:oasis:names:specification:ubl:schema:xsd:Invoice-2'/>")
    assert e.value.kod == "xml-boyut"


def test_svrl_konumu_satira_cevrilir(temel_fatura):
    b = belge.yukle(temel_fatura)
    konum = "/Q{urn:oasis:names:specification:ubl:schema:xsd:Invoice-2}Invoice[1]/Q{urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2}InvoiceLine[1]/Q{urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2}InvoicedQuantity[1]"
    assert b.satir(konum) == 138
    assert b.satir(konum + "/@unitCode") == 138
    assert b.satir("/Q{x}Yok[1]") is None
    assert b.satir("///bozuk[") is None
    assert "local-name()='Invoice'" in belge.svrl_konumu_cevir(konum)


def test_bicimsiz_eksik_alanlar(temel_fatura):
    veri = degistir(
        temel_fatura,
        "<cbc:ProfileID>TEMELFATURA</cbc:ProfileID>",
        "<cbc:ProfileID> </cbc:ProfileID>",
    )
    b = belge.yukle(veri)
    assert b.profil is None and b.tur == "fatura"
