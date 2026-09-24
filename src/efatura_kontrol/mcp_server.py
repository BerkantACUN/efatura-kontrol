from __future__ import annotations

import hmac
import json
import os
import sys
from typing import Annotated, Any

from mcp.types import ToolAnnotations
from pydantic import Field

from efatura_kontrol import PAKET, SURUM
from efatura_kontrol.uret import AZAMI_SATIR, Satir, Senaryo, Taraf

try:
    from mcp.server.mcpserver import MCPServer
except ImportError:
    from mcp.server.fastmcp import FastMCP as MCPServer


def _salt_okur(baslik: str) -> ToolAnnotations:
    """Bütün araçlar yalnız okur, aynı girdiye aynı sonucu verir, ağa çıkmaz."""
    return ToolAnnotations(
        title=baslik,
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    )


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
        "'geçerli' demek GİB'e kesin kabul demek değildir. Akış: belgeyi `belge_dogrula` ile denetle; "
        "açıklaması boş bir bulgu kodu için `bulgu_acikla`; kod listesi hatasında geçerli değerleri "
        "`kod_listesi` ile bul; belgenin içeriği sorulursa `belge_ozeti`. Uzak (HTTP) sunucuda "
        "`dosya` kapalıdır, belgeyi `xml` ile gönder."
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


Dosya = Annotated[
    str | None,
    Field(
        description=(
            "Sunucunun diskindeki UBL-TR XML belgesinin yolu (yalnız yerel stdio sunucusunda). "
            "Uzak (HTTP) sunucuda kapalıdır; orada `xml` kullanın. `xml` verilirse yok sayılır."
        ),
        examples=["C:/faturalar/GIB2026000000001.xml", "/home/ali/fatura.xml"],
    ),
]
Xml = Annotated[
    str | None,
    Field(
        description=(
            "Belgenin tam XML metni (UTF-8; Invoice, DespatchAdvice, ReceiptAdvice, "
            "ApplicationResponse ya da StandardBusinessDocument kökü). En çok 50 MB."
        ),
        examples=[
            '<?xml version="1.0" encoding="UTF-8"?><Invoice xmlns="urn:oasis:names:specification:'
            'ubl:schema:xsd:Invoice-2" ...>...</Invoice>'
        ],
    ),
]


@mcp.tool(title="UBL-TR belgesini doğrula", annotations=_salt_okur("UBL-TR belgesini doğrula"))
def belge_dogrula(
    dosya: Dosya = None,
    xml: Xml = None,
    tur: Annotated[
        str | None,
        Field(
            description=(
                "Belge türünü zorlar: fatura | earsiv | irsaliye | irsaliye-yaniti | "
                "uygulama-yaniti | zarf. Verilmezse kök elemandan ve cbc:ProfileID'den bulunur "
                "(EARSIVFATURA → earsiv). Bilinmeyen değer `tur-bilinmiyor` bulgusu döndürür."
            ),
            examples=["fatura", "earsiv", "irsaliye", "zarf"],
        ),
    ] = None,
) -> dict[str, Any]:
    """Bir UBL-TR e-belgesini GİB'e göndermeden önce GİB'in yayımladığı kurallarla denetler.

    Ne yapar: sırasıyla XML iyi biçimliliği ve boyutu, OASIS UBL 2.1 XSD'si (UBL-TR paketi) ile
    GİB zarf şemaları, GİB e-Fatura Paketi şematronu (kod listeleri dahil), satır / vergi /
    tevkifat / dip toplam aritmetiği ve elektronik imzanın yapısı. Ağa çıkmaz.

    Ne zaman: kullanıcı bir e-Fatura, e-Arşiv fatura, e-İrsaliye, irsaliye yanıtı, uygulama
    yanıtı ya da zarf XML'inin geçerli olup olmadığını, GİB'in neden reddettiğini ya da neyin
    düzeltilmesi gerektiğini sorduğunda. Yalnız içerik (taraflar, tutarlar) soruluyorsa
    `belge_ozeti` daha hızlıdır.

    Girdi: `dosya` (yerel yol) ya da `xml` (belge metni); isteğe bağlı `tur`. Örnekler:
    `{"dosya": "C:/faturalar/fatura.xml"}`, `{"xml": "<Invoice ...>...</Invoice>"}`,
    `{"xml": "<Invoice ...>", "tur": "earsiv"}`.

    Dönüş (JSON nesne): `dosya`; `ozet` = {`gecerli` (hata yoksa true), `hata`, `uyari`,
    `bilgi` sayıları, `tur`, `profil` (senaryo), `tip` (fatura tipi), `sure_ms`}; `paket`
    (kullanılan GİB paket sürümleri); `bulgular[]`, her biri `kod` (ör.
    sch-GeneralUnitCodeCheck-1, xsd-…, hesap-…, imza-…), `seviye` (hata = GİB reddeder;
    uyari = aritmetik/para birimi tutarsızlığı; bilgi = not), `kaynak` (xml/xsd/sematron/hesap/
    imza), `mesaj`, `gib_mesaj` (şematronun özgün metni), `kural` (XPath testi), `konum`
    (XPath), `satir`, `aciklama`, `duzeltme`. Uzak sunucuda `dosya` verilirse
    {`hata`: "uzak-dosya-kapali", `mesaj`} döner.

    English: validates a Turkish UBL-TR e-document offline with the tax authority's own XSD and
    schematron plus arithmetic and signature-structure checks; returns findings with line
    numbers, the original GİB message and a Turkish fix.
    """
    from efatura_kontrol.kontrol import kontrol_et

    try:
        kaynak, ad = _kaynak(dosya, xml)
    except UzakDosyaHatasi as e:
        return {"hata": "uzak-dosya-kapali", "mesaj": str(e)}
    return kontrol_et(kaynak, tur, ad).sozluk()


@mcp.tool(title="UBL-TR belge özeti", annotations=_salt_okur("UBL-TR belge özeti"))
def belge_ozeti(dosya: Dosya = None, xml: Xml = None) -> dict[str, Any]:
    """Bir UBL-TR belgesinin içeriğini yapılandırılmış olarak çıkarır; kural denetimi yapmaz.

    Ne zaman: "bu fatura kime kesilmiş?", "toplam ne kadar?", "hangi senaryo/tip?", "kaç satır
    var?", "imzalı mı?" gibi sorularda ya da doğrulama öncesi doğru belgeye bakıldığını teyit
    etmek için. Geçerlilik soruluyorsa `belge_dogrula` kullanın.

    Girdi: `dosya` (yerel yol) ya da `xml` (belge metni). Örnekler:
    `{"dosya": "C:/faturalar/fatura.xml"}`, `{"xml": "<Invoice ...>...</Invoice>"}`.

    Dönüş (JSON nesne): `dosya`, `tur`, `kokEleman`, `ublSurumu`, `ozellestirme` (TR1.2),
    `senaryo` (cbc:ProfileID), `tip` (cbc:InvoiceTypeCode), `no`, `uuid`, `tarih`, `saat`,
    `paraBirimi`; `satici` ve `alici` = {`unvan`, `vkn`, `tckn`, `vergiDairesi`, `sehir`};
    `satirSayisi`, `satirlar[]` (ilk 50; `no`, `ad`, `miktar`, `birim`, `birimFiyat`, `tutar`,
    `kdvYuzde`); `vergiler[]` (`kod`, `ad`, `matrah`, `yuzde`, `tutar`); `dipToplam`
    (LegalMonetaryTotal alanları); `imzali`; `notlar`. Okunamayan belgede {`hata`, `mesaj`,
    `satir`}; uzak sunucuda `dosya` verilirse {`hata`: "uzak-dosya-kapali"}.

    English: structured summary of a UBL-TR document — scenario, type, parties (tax IDs),
    lines, taxes, totals and whether it is signed. No rule checks.
    """
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


@mcp.tool(title="Bulgu kodunu açıkla", annotations=_salt_okur("Bulgu kodunu açıkla"))
def bulgu_acikla(
    kod: Annotated[
        str,
        Field(
            description=(
                "`belge_dogrula` bulgusundaki `kod` alanı: şematron (sch-<Kural>-<sıra>), XSD "
                "(xsd-…), aritmetik (hesap-…), imza (imza-…) ya da XML (xml-…) kodu."
            ),
            examples=[
                "sch-GeneralUnitCodeCheck-1",
                "hesap-dip-odenecek",
                "xsd-cvc-complex-type-2-4-a",
            ],
        ),
    ],
) -> dict[str, Any]:
    """Bir bulgu kodunun Türkçe açıklamasını ve düzeltme önerisini verir; belge gerektirmez.

    Ne zaman: kullanıcı bir hatanın ne anlama geldiğini ya da nasıl düzeltileceğini sorduğunda,
    ya da `belge_dogrula` bulgusunda `aciklama`/`duzeltme` boş geldiğinde. Kod listesinden bir
    değer gerekiyorsa ardından `kod_listesi` kullanın.

    Girdi örnekleri: `{"kod": "sch-GeneralUnitCodeCheck-1"}`, `{"kod": "hesap-dip-odenecek"}`,
    `{"kod": "xsd-cvc-complex-type-2-4-a"}` (bütün xsd- kodları ortak açıklamaya düşer).

    Dönüş (JSON nesne): {`kod`, `baslik`, `aciklama` (hangi alan neden reddedildi), `duzeltme`}.
    Hazır açıklaması olmayan kodda {`kod`, `aciklama`: null, `not`}: o durumda bulgudaki
    `gib_mesaj` GİB'in kendi açıklamasıdır.

    English: Turkish explanation and suggested fix for a finding code returned by the
    validator.
    """
    from efatura_kontrol import kod as kodlar

    a = kodlar.acikla(kod)
    if a is None:
        return {
            "kod": kod,
            "aciklama": None,
            "not": "Hazır açıklama yok; bulgudaki GİB mesajını kullan",
        }
    return {"kod": kod, **a}


@mcp.tool(title="GİB kod listesi değerleri", annotations=_salt_okur("GİB kod listesi değerleri"))
def kod_listesi(
    liste: Annotated[
        str,
        Field(
            description=(
                "Kod listesinin adı (büyük/küçük harf duyarsız; tek eşleşen alt dize de olur). "
                "Tam liste için `kod_listeleri`."
            ),
            examples=[
                "UnitCodeList",
                "TaxType",
                "WithholdingTaxTypeWithPercent",
                "CurrencyCodeList",
            ],
        ),
    ],
    ara: Annotated[
        str | None,
        Field(
            description="Değerlerde aranacak alt dize; verilmezse bütün değerler döner.",
            examples=["KGM", "0015", "627", "TRY"],
        ),
    ] = None,
) -> dict[str, Any]:
    """GİB şematronunun fiilen uyguladığı bir kod listesinin geçerli değerlerini verir; belge
    gerektirmez.

    Ne zaman: "adet için hangi unitCode?", "KDV'nin vergi kodu ne?", "627 tevkifat kodu geçerli
    mi?", "fatura tipleri neler?" gibi sorularda ya da `belge_dogrula` bir kod listesi hatası
    (ör. sch-GeneralUnitCodeCheck-1) verdiğinde doğru değeri bulmak için.

    Girdi örnekleri: `{"liste": "UnitCodeList", "ara": "KGM"}`, `{"liste": "TaxType"}`,
    `{"liste": "WithholdingTaxTypeWithPercent", "ara": "627"}`.

    Dönüş (JSON nesne): {`liste` (tam adı), `aciklama` (listenin Türkçe açıklaması ve hangi
    alana uygulandığı), `sayi` (eşleşen değer sayısı), `degerler[]`}. Liste bulunamazsa ya da
    ad birden çok listeye uyarsa {`hata`: "Liste bulunamadı: …; adaylar: …"}.

    English: valid values of a GİB code list as enforced by the schematron, optionally
    filtered.
    """
    from efatura_kontrol import kod

    try:
        return kod.liste(liste, ara)
    except KeyError as e:
        return {"hata": e.args[0]}


@mcp.tool(title="GİB kod listeleri ve paket sürümü", annotations=_salt_okur("GİB kod listeleri"))
def kod_listeleri() -> dict[str, Any]:
    """Mevcut GİB kod listelerinin adlarını, Türkçe açıklamalarını ve bu sürümün dayandığı GİB
    paket sürümlerini verir; parametre almaz.

    Ne zaman: hangi kod listelerinin bulunduğunu keşfetmek için (`kod_listesi` öncesi), ya da
    "hangi şematron sürümüyle denetliyorsun?", "UBL-TR kaçıncı sürüm?" sorularında.

    Girdi örneği: `{}`.

    Dönüş (JSON nesne): `paket` = {`ublTr`, `eFaturaPaketi`, `sematronGuncelleme`,
    `kodListeleriKilavuzu`, `indirme`, `kaynak`}; `listeler` = {liste adı: Türkçe açıklama}.

    English: names and Turkish descriptions of the available code lists, and the GİB package
    versions this build validates against.
    """
    from efatura_kontrol import kod

    return {"paket": PAKET, "listeler": kod.liste_adlari()}


ORNEK_SATICI = {
    "vkn_tckn": "1288331521",
    "unvan": "AAA Anonim Şirketi",
    "vergi_dairesi": "Büyük Mükellefler",
    "ilce": "Beşiktaş",
    "sehir": "İstanbul",
}
ORNEK_ALICI = {
    "vkn_tckn": "11111111110",
    "ad": "Ali",
    "soyad": "Yılmaz",
    "ilce": "Çankaya",
    "sehir": "Ankara",
}
ORNEK_SATIR = {
    "ad": "Danışmanlık hizmeti",
    "miktar": "3",
    "birim": "HUR",
    "birim_fiyat": "500",
    "kdv_orani": "20",
}


@mcp.tool(title="Örnek UBL-TR fatura üret", annotations=_salt_okur("Örnek UBL-TR fatura üret"))
def ornek_fatura(
    satici: Annotated[
        Taraf,
        Field(
            description="Satıcı (faturayı düzenleyen): VKN'de unvan, TCKN'de ad/soyad zorunlu.",
            examples=[ORNEK_SATICI],
        ),
    ],
    alici: Annotated[
        Taraf,
        Field(description="Alıcı: VKN'de unvan, TCKN'de ad/soyad zorunlu.", examples=[ORNEK_ALICI]),
    ],
    satirlar: Annotated[
        list[Satir],
        Field(
            min_length=1,
            max_length=AZAMI_SATIR,
            description="En az bir, en çok 1000 satır: ad, miktar, birim (UnitCodeList), KDV "
            "hariç birim fiyat, KDV yüzdesi (> 0).",
            examples=[[ORNEK_SATIR]],
        ),
    ],
    senaryo: Annotated[
        Senaryo,
        Field(
            description="cbc:ProfileID. EARSIVFATURA e-Arşiv kurallarıyla denetlenir.",
            examples=["TEMELFATURA", "TICARIFATURA", "EARSIVFATURA"],
        ),
    ] = "TEMELFATURA",
    no: Annotated[
        str | None,
        Field(
            description="Fatura numarası: 3 karakter seri + 4 hane yıl + 9 hane sıra. Verilmezse "
            "EFK<yıl>000000001.",
            examples=["ABC2026000000123"],
        ),
    ] = None,
    tarih: Annotated[
        str | None,
        Field(
            description="Düzenleme tarihi (YYYY-AA-GG); verilmezse bugün.", examples=["2026-09-24"]
        ),
    ] = None,
) -> dict[str, Any]:
    """Basit girdilerden (taraflar, satırlar, KDV oranı) GİB UBL-TR 1.2 biçiminde örnek bir SATIS
    faturası üretir ve aynı araçla doğrular; hiçbir yere göndermez, dosya yazmaz.

    Ne zaman: kullanıcı test/eğitim için geçerli bir örnek e-Fatura ya da e-Arşiv XML'i
    istediğinde, kendi ürettiği belgeyi karşılaştıracak bir referans aradığında ya da "şu
    satırlarla fatura XML'i nasıl olur?" diye sorduğunda. Var olan bir belgeyi denetlemek için
    `belge_dogrula` kullanın.

    Kapsam: yalnız TRY, KDV oranı > 0; indirim, tevkifat, istisna, döviz yok. Satır tutarı =
    miktar × birim fiyat, KDV = satır tutarı × oran (kuruşa yarım yukarı); dip toplamlar ve
    oran başına KDV alt toplamları hesaplanır. Belge imzasızdır: `ext:ExtensionContent` içinde
    imzanın yerini tutan bir eleman vardır; GİB'e gönderilecek belgeyi entegratör/mali mühür
    imzalar.

    Girdi örneği: `{"satici": {"vkn_tckn": "1288331521", "unvan": "AAA A.Ş.", "ilce":
    "Beşiktaş", "sehir": "İstanbul"}, "alici": {"vkn_tckn": "11111111110", "ad": "Ali",
    "soyad": "Yılmaz", "ilce": "Çankaya", "sehir": "Ankara"}, "satirlar": [{"ad": "Kitap",
    "miktar": "2", "birim_fiyat": "45.50", "kdv_orani": "10"}], "senaryo": "EARSIVFATURA"}`.

    Dönüş (JSON nesne): `xml` (UTF-8 belge metni), `ozet` (`belge_dogrula` özetiyle aynı:
    `gecerli`, `hata`, `uyari`, `bilgi`, `tur`, `profil`, `tip`, `sure_ms`) ve `bulgular[]`
    (yalnız `kod`, `seviye`, `mesaj`; beklenen tek bulgu `imza-yok` bilgisidir). Geçersiz girdi
    (ör. 9 haneli VKN, listede olmayan birim) şema doğrulama hatası olarak döner. VKN/TCKN'nin
    yalnız uzunluğu denetlenir; örnekteki numaralar yer tutucudur, gerçek mükelleflere ait değildir.

    English: builds a valid, unsigned UBL-TR 1.2 sample invoice (TRY, VAT > 0) from simple
    inputs and validates it with this server's own rules.
    """
    import datetime as dt

    from efatura_kontrol.kontrol import kontrol_et
    from efatura_kontrol.uret import FaturaGirdisi
    from efatura_kontrol.uret import ornek_fatura as uret

    girdi = FaturaGirdisi(
        satici=satici,
        alici=alici,
        satirlar=satirlar,
        senaryo=senaryo,
        no=no,
        tarih=dt.date.fromisoformat(tarih) if tarih else None,
    )
    xml = uret(girdi)
    rapor = kontrol_et(xml.encode("utf-8"), None, "<ornek>")
    return {
        "xml": xml,
        "ozet": rapor.sozluk()["ozet"],
        "bulgular": [{"kod": b.kod, "seviye": b.seviye, "mesaj": b.mesaj} for b in rapor.bulgular],
    }


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
