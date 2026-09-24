import json

import pytest

from efatura_kontrol import PAKET
from efatura_kontrol.kontrol import kontrol_et, ozet
from tests.conftest import degistir


def kodlar(rapor, seviye=None):
    return [b.kod for b in rapor.bulgular if seviye is None or b.seviye == seviye]


def test_gecerli_ornekler_gecer(ornekler):
    for ad in ("temel_fatura.xml", "tevkifat_fatura.xml", "earsiv_fatura.xml", "irsaliye.xml"):
        r = kontrol_et(ornekler / ad)
        assert r.gecerli, (ad, r.metin())
        assert kodlar(r) == ["imza-yok"]
        assert r.paket == PAKET and r.sure_ms > 0
    assert kontrol_et(ornekler / "earsiv_fatura.xml").tur == "earsiv"


def test_rapor_sozluk_json_olur(ornekler):
    r = kontrol_et(ornekler / "temel_fatura.xml")
    metin = json.dumps(r.sozluk(), ensure_ascii=False)
    assert '"gecerli": true' in metin and "imza-yok" in metin
    assert r.bulgular[0].sozluk()["aciklama"]


@pytest.mark.parametrize(
    ("eski", "yeni", "beklenen"),
    [
        (
            "<cbc:ID>GIB2026000000001</cbc:ID>",
            "<cbc:ID>GIB-2026-1</cbc:ID>",
            "sch-InvoiceIDCheck-1",
        ),
        (
            'schemeID="TCKN">11111111110<',
            'schemeID="TCKN">1111111111<',
            "sch-PartyIdentificationTCKNVKNCheck-2",
        ),
        (
            'schemeID="VKN">1288331521<',
            'schemeID="VKN">12883315<',
            "sch-PartyIdentificationTCKNVKNCheck-1",
        ),
        ('unitCode="KWH"', 'unitCode="ADET"', "sch-GeneralUnitCodeCheck-1"),
        (
            '<cbc:InvoicedQuantity unitCode="KWH">',
            "<cbc:InvoicedQuantity>",
            "sch-InvoicedQuantityCheck-1",
        ),
        ("<cbc:IssueDate>2026-09-01", "<cbc:IssueDate>2026-13-45", "sch-TarihBicimi-1"),
        ("<cbc:IssueDate>2026-09-01", "<cbc:IssueDate>2099-01-01", "sch-TimeCheck-1"),
        ("<cbc:IssueDate>2026-09-01", "<cbc:IssueDate>2001-01-01", "sch-TimeCheck-2"),
        ("<cbc:ProfileID>TEMELFATURA", "<cbc:ProfileID>TEMEL", "sch-ProfileIDCheck-1"),
        ("<cbc:InvoiceTypeCode>SATIS", "<cbc:InvoiceTypeCode>SATIŞ", "sch-InvoiceTypeCodeCheck-1"),
        (
            "<cbc:DocumentCurrencyCode>TRY",
            "<cbc:DocumentCurrencyCode>USD",
            "sch-CurrencyCodeCheck-6",
        ),
        ("<cbc:TaxTypeCode>0015", "<cbc:TaxTypeCode>9999", "sch-TaxTypeCheck-1"),
        ("<cbc:UBLVersionID>2.1", "<cbc:UBLVersionID>2.0", "sch-UBLVersionIDCheck-1"),
        ("<cbc:InvoiceTypeCode>SATIS", "<cbc:InvoiceTypeCode>IADE", "sch-IADEInvioceCheck-1"),
    ],
)
def test_sematron_hatalari_yakalanir(temel_fatura, eski, yeni, beklenen):
    r = kontrol_et(degistir(temel_fatura, eski, yeni, 3), ad="bozuk.xml")
    assert beklenen in kodlar(r, "hata"), r.metin()
    bulgu = next(b for b in r.bulgular if b.kod == beklenen)
    assert bulgu.satir and bulgu.gib_mesaj and bulgu.kaynak == "sematron"


def test_xsd_hatasi_ve_ozet_bilgisi(temel_fatura):
    r = kontrol_et(
        degistir(
            temel_fatura,
            "<cbc:IssueDate>2026-09-01</cbc:IssueDate>",
            "<cbc:Uydurma>1</cbc:Uydurma>",
        )
    )
    assert any(k.startswith("xsd-") and k != "xsd-ozet" for k in kodlar(r, "hata"))
    assert "xsd-ozet" in kodlar(r, "bilgi")
    hata = next(b for b in r.bulgular if b.kaynak == "xsd" and b.seviye == "hata")
    assert hata.satir and hata.aciklama


def test_bozuk_xml_raporu():
    r = kontrol_et(b"<Invoice", ad="kirik.xml")
    assert not r.gecerli and kodlar(r) == ["xml-bicim"] and r.tur is None
    assert r.bulgular[0].duzeltme


@pytest.mark.parametrize(
    ("eski", "yeni", "beklenen"),
    [
        (
            '<cbc:TaxAmount currencyID="TRY">2.73</cbc:TaxAmount>\n\t\t\t\t<cbc:Percent>18.0',
            '<cbc:TaxAmount currencyID="TRY">2.90</cbc:TaxAmount>\n\t\t\t\t<cbc:Percent>18.0',
            "hesap-vergi",
        ),
        (
            '<cbc:PayableAmount currencyID="TRY">17.88',
            '<cbc:PayableAmount currencyID="TRY">18.88',
            "hesap-dip-odenecek",
        ),
        (
            '<cbc:TaxInclusiveAmount currencyID="TRY">17.88',
            '<cbc:TaxInclusiveAmount currencyID="TRY">17.00',
            "hesap-dip-vergi-dahil",
        ),
        (
            '<cbc:TaxExclusiveAmount currencyID="TRY">15.15',
            '<cbc:TaxExclusiveAmount currencyID="TRY">15.00',
            "hesap-dip-vergi-haric",
        ),
        (
            '<cbc:PriceAmount currencyID="TRY">0.15',
            '<cbc:PriceAmount currencyID="TRY">0.20',
            "hesap-satir",
        ),
        (
            '<cbc:PayableAmount currencyID="TRY">',
            '<cbc:PayableAmount currencyID="USD">',
            "hesap-para-birimi",
        ),
    ],
)
def test_hesap_uyarilari(temel_fatura, eski, yeni, beklenen):
    r = kontrol_et(degistir(temel_fatura, eski, yeni))
    assert beklenen in kodlar(r, "uyari"), r.metin()
    b = next(x for x in r.bulgular if x.kod == beklenen)
    assert b.satir and b.duzeltme and "yazılan" in b.mesaj or beklenen == "hesap-para-birimi"


def test_dip_satir_toplami_ve_vergi_toplami(temel_fatura):
    r = kontrol_et(
        degistir(
            temel_fatura,
            '<cbc:LineExtensionAmount currencyID="TRY">15.15',
            '<cbc:LineExtensionAmount currencyID="TRY">16.15',
        )
    )
    assert "hesap-dip-satir" in kodlar(r, "uyari")
    r = kontrol_et(
        degistir(
            temel_fatura,
            '<cbc:TaxAmount currencyID="TRY">2.73</cbc:TaxAmount>\n\t\t<cac:TaxSubtotal>',
            '<cbc:TaxAmount currencyID="TRY">3.73</cbc:TaxAmount>\n\t\t<cac:TaxSubtotal>',
        )
    )
    assert "hesap-vergi-toplam" in kodlar(r, "uyari")


def test_tevkifat_hesabi(tevkifat_fatura):
    r = kontrol_et(
        degistir(
            tevkifat_fatura,
            '<cbc:TaxAmount currencyID="TRY">3240</cbc:TaxAmount>\n\t\t<cac:TaxSubtotal>',
            '<cbc:TaxAmount currencyID="TRY">3000</cbc:TaxAmount>\n\t\t<cac:TaxSubtotal>',
        )
    )
    assert "hesap-tevkifat-toplam" in kodlar(r, "uyari") and "hesap-dip-odenecek" in kodlar(
        r, "uyari"
    )
    r = kontrol_et(
        degistir(tevkifat_fatura, "<cbc:Percent>90</cbc:Percent>", "<cbc:Percent>50</cbc:Percent>")
    )
    assert "sch-WithholdingTaxTotalCheck-3" in kodlar(r, "hata")
    assert "hesap-tevkifat" in kodlar(r, "uyari")


def test_earsiv_kurallari_tur_parametresiyle(earsiv_fatura, temel_fatura):
    assert kontrol_et(earsiv_fatura).gecerli
    r = kontrol_et(earsiv_fatura, tur="fatura")
    assert "sch-ProfileIDCheck-1" in kodlar(r, "hata")
    r = kontrol_et(temel_fatura, tur="earsiv")
    assert "sch-ProfileIDCheck-2" in kodlar(r, "hata")
    r = kontrol_et(temel_fatura, tur="irsaliye")
    assert "tur-uyumsuz" in kodlar(r, "uyari") and r.tur == "fatura"


def test_imza_yapisi(temel_fatura):
    imza = (
        "<ext:UBLExtensions><ext:UBLExtension><ext:ExtensionContent>"
        '<ds:Signature xmlns:ds="http://www.w3.org/2000/09/xmldsig#" Id="Signature_1"><ds:SignedInfo>'
        '<ds:Reference URI="#yok"/></ds:SignedInfo><ds:SignatureValue>x</ds:SignatureValue></ds:Signature>'
        "</ext:ExtensionContent></ext:UBLExtension></ext:UBLExtensions>\n\t<cbc:UBLVersionID>"
    )
    r = kontrol_et(degistir(temel_fatura, "<cbc:UBLVersionID>", imza))
    k = kodlar(r, "hata")
    assert "imza-yapi" in k and "imza-referans" in k and "imza-yok" not in kodlar(r)
    assert any(x.startswith("sch-XadesSignatureCheckForInvoice") for x in k)


def test_ozet(ornekler, tevkifat_fatura):
    o = ozet(ornekler / "temel_fatura.xml")
    assert o["senaryo"] == "TEMELFATURA" and o["no"] == "GIB2026000000001"
    assert o["satici"]["vkn"] == "1288331521" and o["alici"]["tckn"] == "11111111110"
    assert o["satirSayisi"] == 1 and o["satirlar"][0]["birim"] == "KWH"
    assert o["vergiler"][0]["kod"] == "0015" and o["dipToplam"]["PayableAmount"] == "17.88"
    assert o["imzali"] is False
    t = ozet(tevkifat_fatura)
    assert t["tip"] == "TEVKIFAT" and t["alici"]["unvan"].startswith("British")
    i = ozet(ornekler / "irsaliye.xml")
    assert i["tur"] == "irsaliye" and i["satirSayisi"] >= 1


def test_ozet_irsaliye_ve_yanit_satirlari(irsaliye):
    o = ozet(irsaliye)
    assert o["satirSayisi"] == 4 == len(o["satirlar"])
    assert o["satirlar"][0] == {
        "no": "1",
        "ad": "Masa Üstü Bilgisayar",
        "miktar": "20",
        "birim": "C62",
        "birimFiyat": None,
        "tutar": None,
        "kdvYuzde": None,
    }
    yanit = (
        b'<ReceiptAdvice xmlns="urn:oasis:names:specification:ubl:schema:xsd:ReceiptAdvice-2"'
        b' xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"'
        b' xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">'
        b"<cbc:ID>ABC2026000000001</cbc:ID><cac:ReceiptLine><cbc:ID>1</cbc:ID>"
        b'<cbc:ReceivedQuantity unitCode="KGM">3</cbc:ReceivedQuantity>'
        b"<cac:Item><cbc:Name>Un</cbc:Name></cac:Item></cac:ReceiptLine></ReceiptAdvice>"
    )
    o = ozet(yanit)
    assert o["satirSayisi"] == 1
    assert (o["satirlar"][0]["ad"], o["satirlar"][0]["miktar"], o["satirlar"][0]["birim"]) == (
        "Un",
        "3",
        "KGM",
    )
