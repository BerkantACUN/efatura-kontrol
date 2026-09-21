from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from lxml import etree

from efatura_kontrol.belge import CAC, CBC, Belge
from efatura_kontrol.bulgu import Bulgu

KURUS = Decimal("0.01")
TOLERANS = Decimal("0.01")
YUZ = Decimal(100)
KDV = "0015"
SATIR = CAC + "InvoiceLine"
MIKTAR = CBC + "InvoicedQuantity"
SATIR_TUTARI = CBC + "LineExtensionAmount"
FIYAT = CAC + "Price"
FIYAT_TUTARI = CBC + "PriceAmount"
INDIRIM_ARTIRIM = CAC + "AllowanceCharge"
GOSTERGE = CBC + "ChargeIndicator"
TUTAR = CBC + "Amount"
VERGI_TOPLAMI = CAC + "TaxTotal"
TEVKIFAT_TOPLAMI = CAC + "WithholdingTaxTotal"
VERGI_TUTARI = CBC + "TaxAmount"
VERGI_ALT = CAC + "TaxSubtotal"
MATRAH = CBC + "TaxableAmount"
YUZDE = CBC + "Percent"
VERGI_KODU = CAC + "TaxCategory/" + CAC + "TaxScheme/" + CBC + "TaxTypeCode"
DIP = CAC + "LegalMonetaryTotal"
PARA_BIRIMI = CBC + "DocumentCurrencyCode"
PARA_NITELIGI = "currencyID"
DIP_DISI_PROFILLER = frozenset({"HKS"})


def _sayi(dugum: etree._Element | None) -> Decimal | None:
    if dugum is None or dugum.text is None:
        return None
    try:
        return Decimal(dugum.text.strip())
    except InvalidOperation:
        return None


def _yuvarla(d: Decimal) -> Decimal:
    return d.quantize(KURUS, rounding=ROUND_HALF_UP)


def _uyusmuyor(beklenen: Decimal, bulunan: Decimal) -> bool:
    return abs(_yuvarla(beklenen) - bulunan) > TOLERANS


def _bulgu(
    kod: str, mesaj: str, dugum: etree._Element, beklenen: Decimal, bulunan: Decimal
) -> Bulgu:
    return Bulgu(
        kod=kod,
        seviye="uyari",
        kaynak="hesap",
        mesaj=f"{mesaj}: yazılan {bulunan}, hesaplanan {_yuvarla(beklenen)}",
        konum=dugum.getroottree().getpath(dugum),
        satir=dugum.sourceline,
        deger=str(bulunan),
    )


def _indirim_artirim(kapsayici: etree._Element) -> tuple[Decimal, Decimal]:
    indirim = artirim = Decimal(0)
    for ia in kapsayici.findall(INDIRIM_ARTIRIM):
        tutar = _sayi(ia.find(TUTAR))
        if tutar is None:
            continue
        g = ia.find(GOSTERGE)
        if g is not None and (g.text or "").strip().lower() == "true":
            artirim += tutar
        else:
            indirim += tutar
    return indirim, artirim


def _satirlar(kok: etree._Element, bulgular: list[Bulgu]) -> Decimal:
    toplam = Decimal(0)
    for satir in kok.iterchildren(SATIR):
        tutar = _sayi(satir.find(SATIR_TUTARI))
        miktar = _sayi(satir.find(MIKTAR))
        fiyat = satir.find(FIYAT)
        birim = _sayi(fiyat.find(FIYAT_TUTARI)) if fiyat is not None else None
        if tutar is None:
            continue
        toplam += tutar
        if miktar is None or birim is None:
            continue
        indirim, artirim = _indirim_artirim(satir)
        beklenen = miktar * birim - indirim + artirim
        if _uyusmuyor(beklenen, tutar):
            no = satir.findtext(CBC + "ID", "?")
            bulgular.append(
                _bulgu(
                    "hesap-satir",
                    f"Satır {no} tutarı miktar × birim fiyat − indirim + artırım ile uyuşmuyor",
                    satir.find(SATIR_TUTARI),
                    beklenen,
                    tutar,
                )
            )
        _vergi_toplamlari(satir, bulgular, f"Satır {satir.findtext(CBC + 'ID', '?')} ")
    return toplam


def _alt_toplamlar(vt: etree._Element, bulgular: list[Bulgu], onek: str) -> tuple[Decimal, Decimal]:
    toplam = kdv = Decimal(0)
    for alt in vt.iterchildren(VERGI_ALT):
        tutar = _sayi(alt.find(VERGI_TUTARI))
        if tutar is None:
            continue
        toplam += tutar
        kod = alt.findtext(VERGI_KODU, "").strip()
        if kod == KDV:
            kdv += tutar
        matrah = _sayi(alt.find(MATRAH))
        yuzde = _sayi(alt.find(YUZDE))
        if matrah is not None and yuzde is not None and _uyusmuyor(matrah * yuzde / YUZ, tutar):
            bulgular.append(
                _bulgu(
                    "hesap-vergi",
                    f"{onek}{kod or '?'} vergi tutarı matrah × yüzde ile uyuşmuyor",
                    alt.find(VERGI_TUTARI),
                    matrah * yuzde / YUZ,
                    tutar,
                )
            )
    return toplam, kdv


def _tevkifat(tt: etree._Element, kdv: Decimal, bulgular: list[Bulgu], onek: str) -> Decimal:
    toplam = Decimal(0)
    for alt in tt.iterchildren(VERGI_ALT):
        tutar = _sayi(alt.find(VERGI_TUTARI))
        if tutar is None:
            continue
        toplam += tutar
        yuzde = _sayi(alt.find(YUZDE))
        matrah = _sayi(alt.find(MATRAH))
        taban = matrah if matrah is not None else kdv
        if yuzde is not None and taban and _uyusmuyor(taban * yuzde / YUZ, tutar):
            bulgular.append(
                _bulgu(
                    "hesap-tevkifat",
                    f"{onek}tevkifat tutarı KDV × tevkifat yüzdesi ile uyuşmuyor",
                    alt.find(VERGI_TUTARI),
                    taban * yuzde / YUZ,
                    tutar,
                )
            )
    yazilan = _sayi(tt.find(VERGI_TUTARI))
    if yazilan is None:
        return toplam
    if _uyusmuyor(toplam, yazilan):
        bulgular.append(
            _bulgu(
                "hesap-tevkifat-toplam",
                f"{onek}tevkifat toplamı alt toplamların toplamı ile uyuşmuyor",
                tt.find(VERGI_TUTARI),
                toplam,
                yazilan,
            )
        )
    return yazilan


def _vergi_toplamlari(
    kapsayici: etree._Element, bulgular: list[Bulgu], onek: str = ""
) -> tuple[Decimal, Decimal]:
    vergi = kdv = Decimal(0)
    yazilanlar = []
    for vt in kapsayici.iterchildren(VERGI_TOPLAMI):
        yerel, yerel_kdv = _alt_toplamlar(vt, bulgular, onek)
        vergi += yerel
        kdv += yerel_kdv
        yazilan = _sayi(vt.find(VERGI_TUTARI))
        if yazilan is not None:
            yazilanlar.append((vt, yerel, yazilan))
    tevkifat = sum(
        (_tevkifat(tt, kdv, bulgular, onek) for tt in kapsayici.iterchildren(TEVKIFAT_TOPLAMI)),
        Decimal(0),
    )
    for vt, yerel, yazilan in yazilanlar:
        if _uyusmuyor(yerel, yazilan) and _uyusmuyor(yerel - tevkifat, yazilan):
            bulgular.append(
                _bulgu(
                    "hesap-vergi-toplam",
                    f"{onek}vergi toplamı alt toplamların toplamı (tevkifat düşülmüş ya da düşülmemiş) ile uyuşmuyor",
                    vt.find(VERGI_TUTARI),
                    yerel,
                    yazilan,
                )
            )
    return vergi, tevkifat


def _dip(
    kok: etree._Element,
    satir_toplami: Decimal,
    vergi: Decimal,
    tevkifat: Decimal,
    bulgular: list[Bulgu],
) -> None:
    dip = kok.find(DIP)
    if dip is None:
        return
    indirim, artirim = _indirim_artirim(kok)
    alanlar = {
        ad: _sayi(dip.find(CBC + ad))
        for ad in (
            "LineExtensionAmount",
            "TaxExclusiveAmount",
            "TaxInclusiveAmount",
            "AllowanceTotalAmount",
            "ChargeTotalAmount",
            "PayableRoundingAmount",
            "PayableAmount",
        )
    }
    kontroller = (
        (
            "LineExtensionAmount",
            satir_toplami,
            "hesap-dip-satir",
            "Mal/hizmet toplamı satır tutarlarının toplamı ile uyuşmuyor",
        ),
        (
            "AllowanceTotalAmount",
            indirim,
            "hesap-dip-indirim",
            "Toplam indirim belge indirimlerinin toplamı ile uyuşmuyor",
        ),
        (
            "ChargeTotalAmount",
            artirim,
            "hesap-dip-artirim",
            "Toplam artırım belge artırımlarının toplamı ile uyuşmuyor",
        ),
    )
    for ad, beklenen, kod, mesaj in kontroller:
        yazilan = alanlar[ad]
        if yazilan is not None and _uyusmuyor(beklenen, yazilan):
            bulgular.append(_bulgu(kod, mesaj, dip.find(CBC + ad), beklenen, yazilan))
    satir = (
        alanlar["LineExtensionAmount"]
        if alanlar["LineExtensionAmount"] is not None
        else satir_toplami
    )
    vergi_haric = (
        satir
        - (alanlar["AllowanceTotalAmount"] or indirim)
        + (alanlar["ChargeTotalAmount"] or artirim)
    )
    if alanlar["TaxExclusiveAmount"] is not None and _uyusmuyor(
        vergi_haric, alanlar["TaxExclusiveAmount"]
    ):
        bulgular.append(
            _bulgu(
                "hesap-dip-vergi-haric",
                "Vergi hariç tutar mal/hizmet toplamı − indirim + artırım ile uyuşmuyor",
                dip.find(CBC + "TaxExclusiveAmount"),
                vergi_haric,
                alanlar["TaxExclusiveAmount"],
            )
        )
    vergi_haric = (
        alanlar["TaxExclusiveAmount"] if alanlar["TaxExclusiveAmount"] is not None else vergi_haric
    )
    vergi_dahil = vergi_haric + vergi
    if alanlar["TaxInclusiveAmount"] is not None and _uyusmuyor(
        vergi_dahil, alanlar["TaxInclusiveAmount"]
    ):
        bulgular.append(
            _bulgu(
                "hesap-dip-vergi-dahil",
                "Vergiler dahil tutar vergi hariç tutar + vergiler ile uyuşmuyor",
                dip.find(CBC + "TaxInclusiveAmount"),
                vergi_dahil,
                alanlar["TaxInclusiveAmount"],
            )
        )
    vergi_dahil = (
        alanlar["TaxInclusiveAmount"] if alanlar["TaxInclusiveAmount"] is not None else vergi_dahil
    )
    odenecek = vergi_dahil - tevkifat + (alanlar["PayableRoundingAmount"] or Decimal(0))
    if alanlar["PayableAmount"] is not None and _uyusmuyor(odenecek, alanlar["PayableAmount"]):
        bulgular.append(
            _bulgu(
                "hesap-dip-odenecek",
                "Ödenecek tutar vergiler dahil tutar − tevkifat + yuvarlama ile uyuşmuyor",
                dip.find(CBC + "PayableAmount"),
                odenecek,
                alanlar["PayableAmount"],
            )
        )


def _para_birimi(kok: etree._Element, bulgular: list[Bulgu]) -> None:
    belge_birimi = (kok.findtext(PARA_BIRIMI) or "").strip()
    if not belge_birimi:
        return
    farkli = [d for d in kok.iter() if d.get(PARA_NITELIGI) not in (None, belge_birimi)]
    if farkli:
        ilk = farkli[0]
        bulgular.append(
            Bulgu(
                kod="hesap-para-birimi",
                seviye="uyari",
                kaynak="hesap",
                mesaj=f"{len(farkli)} tutarın currencyID değeri belge para birimi {belge_birimi} ile aynı değil (ilki: {ilk.get(PARA_NITELIGI)})",
                konum=kok.getroottree().getpath(ilk),
                satir=ilk.sourceline,
                deger=ilk.get(PARA_NITELIGI),
            )
        )


def dogrula(belge: Belge) -> list[Bulgu]:
    kok = belge.icerik
    if kok is None or belge.tur not in ("fatura", "earsiv"):
        return []
    bulgular: list[Bulgu] = []
    satir_toplami = _satirlar(kok, bulgular)
    vergi, tevkifat = _vergi_toplamlari(kok, bulgular)
    if belge.profil not in DIP_DISI_PROFILLER:
        _dip(kok, satir_toplami, vergi, tevkifat, bulgular)
    _para_birimi(kok, bulgular)
    return bulgular
