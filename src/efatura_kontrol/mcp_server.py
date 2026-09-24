from __future__ import annotations

import hmac
import json
import os
import sys
from typing import Any

from mcp.types import ToolAnnotations

from efatura_kontrol import PAKET, SURUM

try:
    from mcp.server.mcpserver import MCPServer
except ImportError:
    from mcp.server.fastmcp import FastMCP as MCPServer

SALT_OKUR = ToolAnnotations(readOnlyHint=True, openWorldHint=False)

mcp = MCPServer(
    "efatura-kontrol",
    version=SURUM,
    instructions=(
        "GİB UBL-TR e-belgelerini (e-Fatura, e-Arşiv fatura, e-İrsaliye, uygulama yanıtı, zarf) "
        f"GİB'in kendi XSD ve şematron kurallarıyla (UBL-TR {PAKET['ublTr']}, şematron "
        f"{PAKET['sematronGuncelleme']}) yerelde kontrol eder; hiçbir veri ağa gönderilmez. "
        "'hata' seviyesi GİB'in reddedeceği şeydir; 'uyari' aritmetik/para birimi tutarsızlığıdır "
        "(GİB kabul edebilir, alıcı reddedebilir); 'bilgi' imza durumu gibi notlardır. "
        "Bulguları satır numarası ve düzeltme önerisiyle aktar; imza kriptografik olarak doğrulanmaz, "
        "'geçerli' demek GİB'e kesin kabul demek değildir."
    ),
)


_UZAK_MOD = False


class UzakDosyaHatasi(ValueError):
    pass


def _kaynak(dosya: str | None, xml: str | None) -> tuple[Any, str | None]:
    if xml:
        return xml.encode("utf-8"), "<xml>"
    if dosya:
        if _UZAK_MOD:
            raise UzakDosyaHatasi(
                "Uzak (HTTP) modda dosya parametresi kapalı: sunucu kendi diskini okumaz. "
                "Belgeyi xml parametresiyle gönderin."
            )
        return dosya, None
    raise ValueError("dosya ya da xml verilmeli")


@mcp.tool(annotations=SALT_OKUR)
def belge_dogrula(
    dosya: str | None = None, xml: str | None = None, tur: str | None = None
) -> dict[str, Any]:
    """UBL-TR belgesini denetler: XML biçimi, OASIS UBL 2.1 XSD, GİB e-Fatura şematronu (498 kural,
    kod listeleri dahil), satır/vergi/tevkifat/dip toplam aritmetiği, imza yapısı. Her bulgu: kod,
    seviye (hata/uyari/bilgi), GİB'in özgün mesajı, satır numarası, Türkçe açıklama ve düzeltme.
    `dosya` yerel yol ya da `xml` belge metni; `tur` fatura|earsiv|irsaliye|irsaliye-yaniti|
    uygulama-yaniti|zarf (verilmezse kök elemandan ve ProfileID'den bulunur). Validates a Turkish
    UBL-TR e-invoice with the tax authority's own schematron and returns findings."""
    from efatura_kontrol.kontrol import kontrol_et

    try:
        kaynak, ad = _kaynak(dosya, xml)
    except UzakDosyaHatasi as e:
        return {"hata": "uzak-dosya-kapali", "mesaj": str(e)}
    return kontrol_et(kaynak, tur, ad).sozluk()


@mcp.tool(annotations=SALT_OKUR)
def belge_ozeti(dosya: str | None = None, xml: str | None = None) -> dict[str, Any]:
    """Belgenin kimliği: senaryo, fatura tipi, numara, UUID, tarih, para birimi, satıcı/alıcı
    (VKN/TCKN, unvan), satırlar (ilk 50), vergiler, dip toplamlar, imzalı mı. Summary of a UBL-TR
    document: parties, lines, taxes and totals."""
    from efatura_kontrol.belge import BelgeHatasi
    from efatura_kontrol.kontrol import ozet

    try:
        kaynak, _ = _kaynak(dosya, xml)
    except UzakDosyaHatasi as e:
        return {"hata": "uzak-dosya-kapali", "mesaj": str(e)}
    try:
        return ozet(kaynak)
    except BelgeHatasi as e:
        return {"hata": e.kod, "mesaj": e.mesaj, "satir": e.satir}


@mcp.tool(annotations=SALT_OKUR)
def bulgu_acikla(kod: str) -> dict[str, Any]:
    """Bir bulgu kodunun (örn. sch-GeneralUnitCodeCheck-1, hesap-dip-odenecek) Türkçe açıklaması,
    hangi alanın neden reddedildiği ve nasıl düzeltileceği. Explains a finding code."""
    from efatura_kontrol import kod as kodlar

    a = kodlar.acikla(kod)
    if a is None:
        return {
            "kod": kod,
            "aciklama": None,
            "not": "Hazır açıklama yok; bulgudaki GİB mesajını kullan",
        }
    return {"kod": kod, **a}


@mcp.tool(annotations=SALT_OKUR)
def kod_listesi(liste: str, ara: str | None = None) -> dict[str, Any]:
    """GİB kod listesinin değerleri (şematronun fiilen uyguladığı liste): UnitCodeList, TaxType,
    InvoiceTypeCodeList, ProfileIDType, CurrencyCodeList, WithholdingTaxTypeWithPercent,
    TaxExemptionReasonCodeType, PaymentMeansCodeTypeList... `ara` ile alt dize filtresi. Values of a
    GİB code list as enforced by the schematron."""
    from efatura_kontrol import kod

    try:
        return kod.liste(liste, ara)
    except KeyError as e:
        return {"hata": e.args[0]}


@mcp.tool(annotations=SALT_OKUR)
def kod_listeleri() -> dict[str, Any]:
    """Mevcut GİB kod listelerinin adları ve Türkçe açıklamaları; kaynak paket sürümleri. Names of the
    available code lists and the GİB package versions this build uses."""
    from efatura_kontrol import kod

    return {"paket": PAKET, "listeler": kod.liste_adlari()}


VARSAYILAN_HOST = "0.0.0.0"  # Azure Container Apps'te IPv6 yok; "::" dinlemek başlamayı bozar
VARSAYILAN_PORT = 8080
AZAMI_GOVDE = 64 * 1024 * 1024  # belge sınırı 50 MB; JSON kaçışı ve zarf payı


def _json_yanit(durum: int, veri: dict[str, str]) -> tuple[dict[str, Any], dict[str, Any]]:
    govde = json.dumps(veri, ensure_ascii=False).encode("utf-8")
    baslangic = {
        "type": "http.response.start",
        "status": durum,
        "headers": [
            (b"content-type", b"application/json; charset=utf-8"),
            (b"content-length", str(len(govde)).encode()),
        ],
    }
    return baslangic, {"type": "http.response.body", "body": govde}


class _GovdeFazla(Exception):
    pass


class _BoyutSiniri:
    """İstek gövdesi AZAMI_GOVDE'yi aşarsa 413 döner; gövde SDK'ya ulaşıp belleğe alınmadan kesilir."""

    def __init__(self, uygulama, sinir: int = AZAMI_GOVDE) -> None:
        self.uygulama = uygulama
        self.sinir = sinir

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.uygulama(scope, receive, send)
            return
        uzunluk = dict(scope.get("headers") or []).get(b"content-length")
        if uzunluk is not None and uzunluk.isdigit() and int(uzunluk) > self.sinir:
            for mesaj in _json_yanit(
                413, {"hata": "govde-fazla", "mesaj": "İstek gövdesi çok büyük"}
            ):
                await send(mesaj)
            return
        okunan = 0
        basladi = False

        async def sayan_receive():
            nonlocal okunan
            mesaj = await receive()
            if mesaj["type"] == "http.request":
                okunan += len(mesaj.get("body", b""))
                if okunan > self.sinir:
                    raise _GovdeFazla
            return mesaj

        async def izlenen_send(mesaj):
            nonlocal basladi
            if mesaj["type"] == "http.response.start":
                basladi = True
            await send(mesaj)

        try:
            await self.uygulama(scope, sayan_receive, izlenen_send)
        except _GovdeFazla:
            if not basladi:
                for mesaj in _json_yanit(
                    413, {"hata": "govde-fazla", "mesaj": "İstek gövdesi çok büyük"}
                ):
                    await send(mesaj)


class _AnahtarKapisi:
    """EFATURA_API_KEY verildiğinde her HTTP isteğinde X-API-Key başlığını zorunlu kılar."""

    def __init__(self, uygulama, anahtar: str) -> None:
        self.uygulama = uygulama
        self.anahtar = anahtar.encode("utf-8")

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] == "http":
            verilen = dict(scope.get("headers") or []).get(b"x-api-key", b"")
            if not hmac.compare_digest(verilen, self.anahtar):
                yanit = {"hata": "yetkisiz", "mesaj": "Geçerli bir X-API-Key başlığı gerekli"}
                for mesaj in _json_yanit(401, yanit):
                    await send(mesaj)
                return
        await self.uygulama(scope, receive, send)


def http_uygulamasi(api_anahtari: str | None = None, host: str = VARSAYILAN_HOST):
    """Streamable HTTP ASGI uygulaması (yol: /mcp). Durumsuz: her istek bağımsız, böylece
    birden çok kopya yük dengeleyici arkasında oturum yapışkanlığı olmadan çalışır. Bu süreçte
    `dosya` parametresi kapanır: uzaktaki bir çağıran sunucunun diskindeki dosyaları okuyamasın."""
    global _UZAK_MOD
    _UZAK_MOD = True
    uygulama = _BoyutSiniri(mcp.streamable_http_app(stateless_http=True, host=host))
    return _AnahtarKapisi(uygulama, api_anahtari) if api_anahtari else uygulama


def http_calistir(host: str | None = None, port: int | None = None) -> None:
    import uvicorn

    host = host or os.environ.get("EFATURA_HOST") or VARSAYILAN_HOST
    port = port or int(os.environ.get("EFATURA_PORT") or VARSAYILAN_PORT)
    anahtar = os.environ.get("EFATURA_API_KEY") or None
    if anahtar is None:
        print("uyarı: EFATURA_API_KEY verilmedi; /mcp herkese açık", file=sys.stderr)
    uvicorn.run(http_uygulamasi(anahtar, host), host=host, port=port)


if __name__ == "__main__":
    mcp.run()
