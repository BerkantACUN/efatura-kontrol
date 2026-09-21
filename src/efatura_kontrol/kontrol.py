from __future__ import annotations

import time
from dataclasses import replace
from pathlib import Path
from typing import Any

from efatura_kontrol import PAKET, belge, hesap, imza, kod, sematron, xsd
from efatura_kontrol.belge import CAC, CBC, Belge, BelgeHatasi
from efatura_kontrol.bulgu import Bulgu, Rapor

ESDEGER_TURLER = {"fatura": "earsiv", "earsiv": "fatura"}
_MOTOR_HAZIR = False


def hazirla() -> None:
    global _MOTOR_HAZIR
    if not _MOTOR_HAZIR:
        sematron.motor()
        for tur in xsd.DOSYALAR:
            xsd.sema(tur)
        _MOTOR_HAZIR = True


def _aciklamali(b: Bulgu) -> Bulgu:
    a = kod.acikla(b.kod)
    if a is None or (b.aciklama and b.duzeltme):
        return b
    return replace(b, aciklama=a["aciklama"], duzeltme=a["duzeltme"] or None)


def _tur_uyarisi(istenen: str | None, bulunan: str) -> Bulgu | None:
    if istenen is None or istenen == bulunan or ESDEGER_TURLER.get(istenen) == bulunan:
        return None
    return Bulgu(
        kod="tur-uyumsuz",
        seviye="uyari",
        kaynak="xml",
        mesaj=f"İstenen tür {istenen}, belgenin kök elemanı {bulunan} türünde; kontrol {bulunan} kurallarıyla yapıldı",
    )


def kontrol_et(kaynak: str | Path | bytes, tur: str | None = None, ad: str | None = None) -> Rapor:
    baslangic = time.perf_counter()
    dosya = ad or (kaynak if isinstance(kaynak, str) else getattr(kaynak, "name", "<bellek>"))
    try:
        b = belge.yukle(kaynak, ad, tur)
    except BelgeHatasi as e:
        rapor = Rapor(str(dosya), None, paket=dict(PAKET))
        rapor.ekle(_aciklamali(Bulgu(e.kod, "hata", "xml", e.mesaj, satir=e.satir)))
        rapor.sure_ms = (time.perf_counter() - baslangic) * 1000
        return rapor
    rapor = Rapor(b.ad, b.tur, b.profil, b.tip, paket=dict(PAKET))
    uyari = _tur_uyarisi(tur, b.tur)
    if uyari:
        rapor.ekle(uyari)
    xsd_bulgulari = xsd.dogrula(b)
    rapor.ekle(*xsd_bulgulari)
    if xsd_bulgulari:
        rapor.ekle(
            Bulgu(
                kod="xsd-ozet",
                seviye="bilgi",
                kaynak="xsd",
                mesaj=f"{len(xsd_bulgulari)} şema hatası var; şematron ve hesap sonuçları yapı düzelene kadar eksik olabilir",
            )
        )
    rapor.ekle(*sematron.dogrula(b))
    rapor.ekle(*hesap.dogrula(b))
    rapor.ekle(*imza.dogrula(b))
    rapor.bulgular = [_aciklamali(x) for x in rapor.bulgular]
    rapor.sirala()
    rapor.sure_ms = (time.perf_counter() - baslangic) * 1000
    return rapor


def _taraf(kok, ad: str) -> dict[str, Any] | None:
    taraf = kok.find(CAC + ad + "/" + CAC + "Party")
    if taraf is None:
        return None
    kimlikler = {
        k.get("schemeID") or "": (k.text or "").strip()
        for k in taraf.iterfind(CAC + "PartyIdentification/" + CBC + "ID")
    }
    kisi = taraf.find(CAC + "Person")
    unvan = taraf.findtext(CAC + "PartyName/" + CBC + "Name")
    if not unvan and kisi is not None:
        unvan = " ".join(
            p for p in (kisi.findtext(CBC + "FirstName"), kisi.findtext(CBC + "FamilyName")) if p
        )
    return {
        "unvan": (unvan or "").strip() or None,
        "vkn": kimlikler.get("VKN"),
        "tckn": kimlikler.get("TCKN"),
        "vergiDairesi": (
            taraf.findtext(CAC + "PartyTaxScheme/" + CAC + "TaxScheme/" + CBC + "Name") or ""
        ).strip()
        or None,
        "sehir": (taraf.findtext(CAC + "PostalAddress/" + CBC + "CityName") or "").strip() or None,
    }


def _dip(kok) -> dict[str, str]:
    dip = kok.find(CAC + "LegalMonetaryTotal")
    if dip is None:
        return {}
    return {c.tag.rsplit("}", 1)[1]: (c.text or "").strip() for c in dip}


def _vergiler(kok) -> list[dict[str, str | None]]:
    sonuc = []
    for alt in kok.iterfind(CAC + "TaxTotal/" + CAC + "TaxSubtotal"):
        sonuc.append(
            {
                "kod": (
                    alt.findtext(CAC + "TaxCategory/" + CAC + "TaxScheme/" + CBC + "TaxTypeCode")
                    or ""
                ).strip(),
                "ad": (
                    alt.findtext(CAC + "TaxCategory/" + CAC + "TaxScheme/" + CBC + "Name") or ""
                ).strip()
                or None,
                "matrah": (alt.findtext(CBC + "TaxableAmount") or "").strip(),
                "yuzde": (alt.findtext(CBC + "Percent") or "").strip() or None,
                "tutar": (alt.findtext(CBC + "TaxAmount") or "").strip(),
            }
        )
    return sonuc


def _satirlar(kok, sinir: int) -> list[dict[str, str | None]]:
    sonuc = []
    for s in kok.iterfind(CAC + "InvoiceLine"):
        if len(sonuc) >= sinir:
            break
        miktar = s.find(CBC + "InvoicedQuantity")
        sonuc.append(
            {
                "no": (s.findtext(CBC + "ID") or "").strip(),
                "ad": (s.findtext(CAC + "Item/" + CBC + "Name") or "").strip(),
                "miktar": (miktar.text or "").strip() if miktar is not None else None,
                "birim": miktar.get("unitCode") if miktar is not None else None,
                "birimFiyat": (s.findtext(CAC + "Price/" + CBC + "PriceAmount") or "").strip()
                or None,
                "tutar": (s.findtext(CBC + "LineExtensionAmount") or "").strip() or None,
                "kdvYuzde": (
                    s.findtext(CAC + "TaxTotal/" + CAC + "TaxSubtotal/" + CBC + "Percent") or ""
                ).strip()
                or None,
            }
        )
    return sonuc


def ozet(kaynak: str | Path | bytes, satir_siniri: int = 50) -> dict[str, Any]:
    b: Belge = belge.yukle(kaynak)
    kok = b.icerik
    if kok is None:
        return {"dosya": b.ad, "tur": b.tur, "icerik": None}

    def metin(ad: str) -> str | None:
        return (kok.findtext(CBC + ad) or "").strip() or None

    satir_sayisi = sum(1 for _ in kok.iterfind(CAC + "InvoiceLine")) or sum(
        1 for _ in kok.iterfind(CAC + "DespatchLine")
    )
    return {
        "dosya": b.ad,
        "tur": b.tur,
        "kokEleman": b.kok.tag.rsplit("}", 1)[1],
        "ublSurumu": metin("UBLVersionID"),
        "ozellestirme": metin("CustomizationID"),
        "senaryo": b.profil,
        "tip": b.tip,
        "no": metin("ID"),
        "uuid": metin("UUID"),
        "tarih": metin("IssueDate"),
        "saat": metin("IssueTime"),
        "paraBirimi": metin("DocumentCurrencyCode"),
        "satici": _taraf(kok, "AccountingSupplierParty") or _taraf(kok, "DespatchSupplierParty"),
        "alici": _taraf(kok, "AccountingCustomerParty") or _taraf(kok, "DeliveryCustomerParty"),
        "satirSayisi": satir_sayisi,
        "satirlar": _satirlar(kok, satir_siniri),
        "vergiler": _vergiler(kok),
        "dipToplam": _dip(kok),
        "imzali": bool(imza._IMZALAR(kok)),
        "notlar": [(n.text or "").strip() for n in kok.iterfind(CBC + "Note")][:10],
    }
