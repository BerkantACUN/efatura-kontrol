"""Basit girdilerden (taraflar, satırlar, KDV oranı) GİB UBL-TR 1.2 örnek fatura üretir.

Amaç test ve öğrenme: üretilen belge bu aracın kendi doğrulamasından (XSD, GİB şematronu,
aritmetik) hatasız geçer. İmzasızdır ("imza-yok" bilgisi); GİB'e gönderilecek belgeyi
entegratör ya da mali mühür imzalar. Kapsam bilinçli olarak dar: TRY, KDV oranı > 0,
indirim/tevkifat/istisna yok.
"""

from __future__ import annotations

import datetime as dt
import uuid as uuid_mod
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

from lxml import etree
from pydantic import BaseModel, Field, field_validator, model_validator

from efatura_kontrol import kod

NS_INV = "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
NS_CAC = "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
NS_CBC = "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2"
NS_EXT = "urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2"
NS_YER = "urn:efatura-kontrol:ornek"  # imzasız örnekte ds:Signature'ın yerini tutar
NSMAP = {None: NS_INV, "cac": NS_CAC, "cbc": NS_CBC, "ext": NS_EXT}
KURUS = Decimal("0.01")


class Taraf(BaseModel):
    """Satıcı ya da alıcı."""

    vkn_tckn: str = Field(
        description="10 haneli VKN (tüzel kişi) ya da 11 haneli TCKN (gerçek kişi).",
        examples=["1288331521", "11111111110"],
    )
    unvan: str | None = Field(
        None,
        description="Tüzel kişinin unvanı (VKN'de zorunlu).",
        examples=["AAA Anonim Şirketi"],
    )
    ad: str | None = Field(
        None, description="Gerçek kişinin adı (TCKN'de zorunlu).", examples=["Ali"]
    )
    soyad: str | None = Field(
        None, description="Gerçek kişinin soyadı (TCKN'de zorunlu).", examples=["Yılmaz"]
    )
    vergi_dairesi: str | None = Field(
        None, description="Vergi dairesi adı.", examples=["Büyük Mükellefler"]
    )
    adres: str | None = Field(
        None, description="Cadde/sokak ve numara.", examples=["Papatya Caddesi No:21"]
    )
    ilce: str = Field(description="İlçe.", examples=["Beşiktaş"])
    sehir: str = Field(description="İl.", examples=["İstanbul"])
    ulke: str = Field("Türkiye", description="Ülke adı.", examples=["Türkiye"])

    @field_validator("vkn_tckn")
    @classmethod
    def _numara(cls, v: str) -> str:
        v = v.strip()
        if not (v.isdigit() and len(v) in (10, 11)):
            raise ValueError("vkn_tckn 10 (VKN) ya da 11 (TCKN) haneli olmalı")
        return v

    @model_validator(mode="after")
    def _kimlik(self) -> Taraf:
        if self.tuzel and not self.unvan:
            raise ValueError("VKN'li tarafta unvan zorunlu")
        if not self.tuzel and not (self.ad and self.soyad):
            raise ValueError("TCKN'li tarafta ad ve soyad zorunlu")
        return self

    @property
    def tuzel(self) -> bool:
        return len(self.vkn_tckn) == 10


class Satir(BaseModel):
    """Fatura satırı."""

    ad: str = Field(description="Mal/hizmet adı.", examples=["Danışmanlık hizmeti"])
    miktar: Decimal = Field(gt=0, description="Miktar.", examples=["1", "2.5"])
    birim: str = Field(
        "C62",
        description="UN/ECE birim kodu (GİB UnitCodeList): C62 adet, KGM kilogram, LTR litre, "
        "HUR saat, MTR metre…",
        examples=["C62", "KGM", "HUR"],
    )
    birim_fiyat: Decimal = Field(
        ge=0, description="KDV hariç birim fiyat.", examples=["100", "12.5"]
    )
    kdv_orani: Decimal = Field(
        Decimal(20),
        gt=0,
        le=100,
        description="KDV yüzdesi. 0 (istisna) bu üreticide desteklenmez.",
        examples=["20", "10", "1"],
    )

    @field_validator("birim")
    @classmethod
    def _birim(cls, v: str) -> str:
        v = v.strip().upper()
        if not kod.gecerli_mi("UnitCodeList", v):
            raise ValueError(f"{v} GİB UnitCodeList'te yok (adet için C62)")
        return v


Senaryo = Literal["TEMELFATURA", "TICARIFATURA", "EARSIVFATURA"]


class FaturaGirdisi(BaseModel):
    satici: Taraf
    alici: Taraf
    satirlar: list[Satir] = Field(min_length=1)
    senaryo: Senaryo = "TEMELFATURA"
    no: str | None = None
    tarih: dt.date | None = None
    uuid: str | None = None
    notlar: list[str] = Field(default_factory=list)


def _para(d: Decimal) -> str:
    return str(d.quantize(KURUS, rounding=ROUND_HALF_UP))


def _sayi(d: Decimal) -> str:
    return format(d.normalize(), "f")


class _Yazar:
    def __init__(self) -> None:
        self.kok = etree.Element(f"{{{NS_INV}}}Invoice", nsmap=NSMAP)

    @staticmethod
    def e(ust, ad: str, metin: str | None = None, **nitelik) -> etree._Element:
        on, yerel = ad.split(":")
        dugum = etree.SubElement(ust, f"{{{NS_CAC if on == 'cac' else NS_CBC}}}{yerel}", nitelik)
        if metin is not None:
            dugum.text = metin
        return dugum


def _taraf(y: _Yazar, ust, t: Taraf) -> None:
    parti = y.e(ust, "cac:Party")
    kimlik = y.e(parti, "cac:PartyIdentification")
    y.e(kimlik, "cbc:ID", t.vkn_tckn, schemeID="VKN" if t.tuzel else "TCKN")
    if t.tuzel:
        y.e(y.e(parti, "cac:PartyName"), "cbc:Name", t.unvan)
    adres = y.e(parti, "cac:PostalAddress")
    if t.adres:
        y.e(adres, "cbc:StreetName", t.adres)
    y.e(adres, "cbc:CitySubdivisionName", t.ilce)
    y.e(adres, "cbc:CityName", t.sehir)
    y.e(y.e(adres, "cac:Country"), "cbc:Name", t.ulke)
    if t.vergi_dairesi:
        vergi = y.e(parti, "cac:PartyTaxScheme")
        y.e(y.e(vergi, "cac:TaxScheme"), "cbc:Name", t.vergi_dairesi)
    if not t.tuzel:
        kisi = y.e(parti, "cac:Person")
        y.e(kisi, "cbc:FirstName", t.ad)
        y.e(kisi, "cbc:FamilyName", t.soyad)


def _vergi_alt(y: _Yazar, ust, matrah: Decimal, vergi: Decimal, oran: Decimal) -> None:
    alt = y.e(ust, "cac:TaxSubtotal")
    y.e(alt, "cbc:TaxableAmount", _para(matrah), currencyID="TRY")
    y.e(alt, "cbc:TaxAmount", _para(vergi), currencyID="TRY")
    y.e(alt, "cbc:Percent", _sayi(oran))
    sema = y.e(y.e(alt, "cac:TaxCategory"), "cac:TaxScheme")
    y.e(sema, "cbc:Name", "KDV")
    y.e(sema, "cbc:TaxTypeCode", "0015")


def ornek_fatura(girdi: FaturaGirdisi | dict) -> str:
    """UBL-TR 1.2 fatura XML'i (UTF-8 metin) döndürür."""
    g = girdi if isinstance(girdi, FaturaGirdisi) else FaturaGirdisi.model_validate(girdi)
    tarih = g.tarih or dt.date.today()
    no = g.no or f"EFK{tarih.year}{1:09d}"
    y = _Yazar()
    k = y.kok
    # GİB XSD'sinde UBLExtensions zorunlu; imzalanınca ExtensionContent'e ds:Signature girer
    icerik = etree.SubElement(
        etree.SubElement(
            etree.SubElement(k, f"{{{NS_EXT}}}UBLExtensions"), f"{{{NS_EXT}}}UBLExtension"
        ),
        f"{{{NS_EXT}}}ExtensionContent",
    )
    etree.SubElement(icerik, f"{{{NS_YER}}}ImzaYeri", nsmap={"ornek": NS_YER})
    y.e(k, "cbc:UBLVersionID", "2.1")
    y.e(k, "cbc:CustomizationID", "TR1.2")
    y.e(k, "cbc:ProfileID", g.senaryo)
    y.e(k, "cbc:ID", no)
    y.e(k, "cbc:CopyIndicator", "false")
    y.e(k, "cbc:UUID", (g.uuid or str(uuid_mod.uuid4())).upper())
    y.e(k, "cbc:IssueDate", tarih.isoformat())
    y.e(k, "cbc:InvoiceTypeCode", "SATIS")
    for n in g.notlar:
        y.e(k, "cbc:Note", n)
    y.e(k, "cbc:DocumentCurrencyCode", "TRY")
    y.e(k, "cbc:LineCountNumeric", str(len(g.satirlar)))

    imza = y.e(k, "cac:Signature")
    y.e(imza, "cbc:ID", g.satici.vkn_tckn, schemeID="VKN_TCKN")
    imzaci = y.e(imza, "cac:SignatoryParty")
    y.e(
        y.e(imzaci, "cac:PartyIdentification"),
        "cbc:ID",
        g.satici.vkn_tckn,
        schemeID="VKN" if g.satici.tuzel else "TCKN",
    )
    adres = y.e(imzaci, "cac:PostalAddress")
    y.e(adres, "cbc:CitySubdivisionName", g.satici.ilce)
    y.e(adres, "cbc:CityName", g.satici.sehir)
    y.e(y.e(adres, "cac:Country"), "cbc:Name", g.satici.ulke)
    y.e(
        y.e(y.e(imza, "cac:DigitalSignatureAttachment"), "cac:ExternalReference"),
        "cbc:URI",
        "#Signature",
    )

    _taraf(y, y.e(k, "cac:AccountingSupplierParty"), g.satici)
    _taraf(y, y.e(k, "cac:AccountingCustomerParty"), g.alici)

    tutarlar = []
    oranlar: dict[Decimal, list[Decimal]] = {}
    for s in g.satirlar:
        tutar = (s.miktar * s.birim_fiyat).quantize(KURUS, rounding=ROUND_HALF_UP)
        vergi = (tutar * s.kdv_orani / 100).quantize(KURUS, rounding=ROUND_HALF_UP)
        tutarlar.append((tutar, vergi))
        oranlar.setdefault(s.kdv_orani, [Decimal(0), Decimal(0)])
        oranlar[s.kdv_orani][0] += tutar
        oranlar[s.kdv_orani][1] += vergi
    toplam = sum((t for t, _ in tutarlar), Decimal(0))
    vergi_toplam = sum((v for _, v in tutarlar), Decimal(0))

    vt = y.e(k, "cac:TaxTotal")
    y.e(vt, "cbc:TaxAmount", _para(vergi_toplam), currencyID="TRY")
    for oran in sorted(oranlar):
        matrah, vergi = oranlar[oran]
        _vergi_alt(y, vt, matrah, vergi, oran)

    dip = y.e(k, "cac:LegalMonetaryTotal")
    y.e(dip, "cbc:LineExtensionAmount", _para(toplam), currencyID="TRY")
    y.e(dip, "cbc:TaxExclusiveAmount", _para(toplam), currencyID="TRY")
    y.e(dip, "cbc:TaxInclusiveAmount", _para(toplam + vergi_toplam), currencyID="TRY")
    y.e(dip, "cbc:PayableAmount", _para(toplam + vergi_toplam), currencyID="TRY")

    for no_, (s, (tutar, vergi)) in enumerate(zip(g.satirlar, tutarlar, strict=True), 1):
        sat = y.e(k, "cac:InvoiceLine")
        y.e(sat, "cbc:ID", str(no_))
        y.e(sat, "cbc:InvoicedQuantity", _sayi(s.miktar), unitCode=s.birim)
        y.e(sat, "cbc:LineExtensionAmount", _para(tutar), currencyID="TRY")
        svt = y.e(sat, "cac:TaxTotal")
        y.e(svt, "cbc:TaxAmount", _para(vergi), currencyID="TRY")
        _vergi_alt(y, svt, tutar, vergi, s.kdv_orani)
        y.e(y.e(sat, "cac:Item"), "cbc:Name", s.ad)
        y.e(y.e(sat, "cac:Price"), "cbc:PriceAmount", _sayi(s.birim_fiyat), currencyID="TRY")

    return etree.tostring(k, xml_declaration=True, encoding="UTF-8", pretty_print=True).decode(
        "utf-8"
    )
