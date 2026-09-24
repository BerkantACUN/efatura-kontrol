# efatura-kontrol

GİB'e göndermeden önce e-Fatura, e-Arşiv Fatura, e-İrsaliye ve zarf dosyalarını **GİB'in kendi kurallarıyla** kontrol eder: OASIS UBL 2.1 XSD'si, GİB'in e-Fatura Paketi şematronu (498 kural, 41 kod listesi), satır/vergi/tevkifat/dip toplam aritmetiği ve imza yapısı. Her bulgu satır numarası, GİB'in özgün mesajı, Türkçe açıklama ve düzeltme önerisiyle gelir. Komut satırı, Python kütüphanesi ve MCP sunucusu; hiçbir veri ağa gitmez.

*Validates Turkish UBL-TR e-invoices (e-Fatura, e-Arşiv, e-İrsaliye, envelopes) offline with the Revenue Administration's own XSD and schematron rules, plus arithmetic and signature-structure checks; explains every finding in Turkish with a fix. CLI, Python API and MCP server.*

mcp-name: io.github.BerkantACUN/efatura-kontrol

```
$ efatura-kontrol dogrula fatura.xml
fatura.xml: GEÇERSİZ — 1 hata, 1 uyarı, 1 bilgi (fatura / TEMELFATURA / SATIS, 6.2 ms)
  HATA  sch-GeneralUnitCodeCheck-1 [satır 138]: Geçersiz unitCode niteliği : 'ADET'. Geçerli değerler için kod listesine bakınız.
        → Adet için C62, kilogram KGM, gram GRM, metre MTR, litre LTR, saat HUR, gün DAY, ay MON, kutu BX, paket PA, çift PR yazın.
  UYARI hesap-dip-odenecek [satır 134]: Ödenecek tutar vergiler dahil tutar − tevkifat + yuvarlama ile uyuşmuyor: yazılan 18.88, hesaplanan 17.88
        → Tevkifatlı faturada tevkifatı düşün; yuvarlama varsa PayableRoundingAmount yazın.
  BILGI imza-yok [satır 3]: Belge elektronik imza taşımıyor; GİB'e gönderilecek belgede XAdES imzası bulunmalıdır, taslak için normaldir
```

## Neden

GİB'in şematronu XPath 2.0 ile yazılmış, üç dosyaya bölünmüş, 133 soyut kural ve parça-içerme kullanır; sıradan araçlarla (lxml, çoğu Python şematron kütüphanesi) çalışmaz. Bu yüzden entegratörler hatayı ancak GİB'e ya da özel entegratöre gönderince öğrenir. efatura-kontrol GİB'in şematronunu düzleştirip XSLT 3.0'a bir kez derler (SchXslt2), Saxon ile çalıştırır: belge başına 2–20 ms, GİB'in verdiği mesajın aynısı, üstüne satır numarası ve düzeltme.

## Kurulum

```bash
uvx efatura-kontrol --help          # kurulumsuz
pip install efatura-kontrol         # ya da kalıcı
```

Python ≥ 3.10; bağımlılıklar lxml ve SaxonC-HE (`saxonche`, ~40 MB wheel; Windows, macOS, Linux). İlk çalıştırma şematronu derlerken ~0,5 s alır, sonrası milisaniyeler.

## Komutlar

| Komut | Ne yapar |
|---|---|
| `dogrula belge.xml [belge2.xml…] [--tur fatura\|earsiv\|irsaliye\|irsaliye-yaniti\|uygulama-yaniti\|zarf] [--json] [--sessiz]` | Tam denetim; hata varsa çıkış kodu 1 |
| `ozet belge.xml` | Senaryo, tip, numara, taraflar (VKN/TCKN), satırlar, vergiler, dip toplamlar, imzalı mı |
| `kod` / `kod UnitCodeList --ara KGM` | GİB kod listeleri (şematronun fiilen uyguladığı değerler) |
| `acikla sch-GeneralUnitCodeCheck-1` | Bulgu kodunun açıklaması ve düzeltmesi |
| `toplu klasor/ [--isci 8] [--json]` | Klasördeki tüm XML'leri paralel denetle; 200 belge (22 MB) ≈ 2 s |
| `mcp [--http] [--host H] [--port P]` | MCP sunucusu (stdio; `--http` ile streamable HTTP) |

Belge türü kök elemandan ve `cbc:ProfileID`'den bulunur; `EARSIVFATURA` görünce e-Arşiv kuralları (`type=earchive`) uygulanır. `--tur` ile zorlanabilir.

## MCP sunucusu

Claude Desktop / Claude Code / Cursor için:

```json
{
  "mcpServers": {
    "efatura-kontrol": { "command": "uvx", "args": ["efatura-kontrol", "mcp"] }
  }
}
```

Araçlar (hepsi salt okunur): `belge_dogrula(dosya|xml, tur)`, `belge_ozeti(dosya|xml)`, `bulgu_acikla(kod)`, `kod_listesi(liste, ara)`, `kod_listeleri()`. Resmî MCP kayıt defterinde `io.github.BerkantACUN/efatura-kontrol`.

## Uzak sunucu (Docker)

`efatura-kontrol mcp --http` sunucuyu streamable HTTP ile `http://<host>:8080/mcp` adresinde açar (durumsuz; birden çok kopya yük dengeleyici arkasında çalışır). Hazır imaj her `v*` sürümünde yayımlanır:

```bash
docker run --rm -p 8080:8080 -e EFATURA_API_KEY=gizli ghcr.io/berkantacun/efatura-kontrol
```

| Ortam değişkeni | Varsayılan | Anlamı |
|---|---|---|
| `EFATURA_HOST` | `0.0.0.0` | Dinlenecek adres (Azure Container Apps IPv6 desteklemediği için IPv4) |
| `EFATURA_PORT` | `8080` | Port |
| `EFATURA_API_KEY` | — | Verilirse her istekte `X-API-Key` başlığı bu değere eşit olmalı, yoksa 401 |

İstemci tarafı:

```json
{
  "mcpServers": {
    "efatura-kontrol": {
      "type": "http",
      "url": "https://sunucu.example.com/mcp",
      "headers": { "X-API-Key": "gizli" }
    }
  }
}
```

Uzak modda `dosya` parametresi kapalıdır (sunucu kendi diskini okumaz, `uzak-dosya-kapali` hatası döner); belgeyi `xml` parametresiyle gönderin. İstek gövdesi 64 MB ile sınırlıdır. Anahtar yalnız basit bir paylaşımlı sırdır; sunucuyu internete açarken TLS sonlandıran bir ters vekil (Container Apps ingress gibi) arkasında çalıştırın.

## Python

```python
from efatura_kontrol.kontrol import kontrol_et, ozet

rapor = kontrol_et("fatura.xml")  # ya da bytes, tur="earsiv"
rapor.gecerli, rapor.sayim("hata"), rapor.sozluk()
for b in rapor.bulgular:
    print(b.seviye, b.kod, b.satir, b.mesaj, b.duzeltme)
```

## Ne kontrol edilir

| Katman | Kaynak | Seviye |
|---|---|---|
| XML iyi biçimlilik, boyut (≤ 50 MB), kök eleman | lxml | hata |
| XSD | OASIS UBL 2.1 runtime şemaları (UBL-TR 1.2.1 paketi) + GİB zarf/HRXML şemaları | hata |
| Şematron | GİB e-Fatura Paketi (29), `UBL-TR_Main/Common/Codelist`, şematron güncellemesi 2026-07-01; 121 kural, 499 assert, 41 kod listesi (birim, para birimi, ülke, vergi, tevkifat kod+oran, istisna, ödeme şekli, senaryo, fatura tipi…) | hata |
| Aritmetik | satır tutarı = miktar × fiyat − indirim + artırım; vergi = matrah × oran; vergi toplamı; tevkifat = KDV × oran; dip toplamlar (mal/hizmet, indirim, artırım, vergi hariç, vergiler dahil, ödenecek); currencyID tutarlılığı | uyarı |
| İmza | ds:Signature var mı, SignedInfo/SignatureValue/X509Certificate/SigningTime/SigningCertificate, Reference URI'leri çözülüyor mu | hata/bilgi |

"Uyarı" GİB'in reddetmeyebileceği ama alıcının reddedeceği şeydir; "bilgi" imza durumu gibi notlardır. HKS (hal) faturalarında dip toplam kuralları farklı olduğundan aritmetik dip kontrolü atlanır.

## Bulgu biçimi

```json
{"kod": "sch-GeneralUnitCodeCheck-1", "seviye": "hata", "kaynak": "sematron",
 "mesaj": "Geçersiz unitCode niteliği : 'ADET'. …", "gib_mesaj": "…",
 "kural": "not(//cbc:UBLVersionID = '2.1') or contains($UnitCodeList, …)",
 "konum": "/Q{…}Invoice[1]/Q{…}InvoiceLine[1]/Q{…}InvoicedQuantity[1]/@unitCode",
 "satir": 138, "aciklama": "…", "duzeltme": "Adet için C62, …"}
```

Şematron bulgu kodları GİB'in soyut kural adından türetilir (`sch-<KuralAdı>-<sıra>`); GİB kural sırasını değiştirirse kod kayar, mesaj aynı kalır.

## GİB'in kendi örneklerinde sonuç

UBL-TR 1.2.1 paketindeki örnekler (hiçbir şey değiştirmeden):

| Örnek | Sonuç |
|---|---|
| IDIS_Fatura, SARJ, SARJANLIK, OTV, OZELMATRAH, YTB_* (12 dosya), HKS-Ornek1 (şematron) | geçerli |
| TemelFaturaOrnegi | fatura numarası biçimi (`ABC2009123456789` kalıbı), 10 haneli TCKN |
| TEVKIFAT, ISTISNA-2, HASTANE | `unitCode` yok (paket örnekleri 2022 öncesi kurala göre) |
| ISTISNA-1/2 | TRY dışı para biriminde kur yok |
| IadeFaturasiOrnegi | TICARIFATURA'da IADE olmaz; iade referansı eksik |
| IHRACAT | imza yapısı eksik (örnek imzasız kesilmiş) |
| HKS-Ornek1/2 | XSD: boş `ext:ExtensionContent` |
| e-FaturaPaketi/xml/* | UBL 2.0 / TR1.0 eski örnekler, şematron reddediyor |

Yani araç GİB'in kendi paketindeki eskimiş örnekleri bile yakalıyor; `ornekler/` altında düzeltilmiş, tam geçerli dört belge var.

## Güncel kalma

`araclar/paket_indir.py` GİB paketlerini indirir (sha256 ile), `efatura-kontrol derle kaynak` şematronu düzleştirip derler, kod listelerini ve XSD'leri `ekler/` altına yazar. CI her çalıştığında güncel GİB paketiyle üretilen çıktının repodakiyle aynı olduğunu doğrular; GİB paketi değiştiğinde iş kırmızıya döner ve yeni sürüm çıkar. Kullanılan paket sürümleri `efatura_kontrol.PAKET` içinde ve her raporun `paket` alanında.

## Sınırlar

- İmza kriptografik olarak doğrulanmaz (sertifika, özet, zaman damgası); yalnız yapısı denetlenir.
- GİB'in **canlı** kontrolleri (mükellef kayıtlı mı, etiket geçerli mi, faaliyet kodu–KDV oranı eşleşmesi, mükerrer numara) bu araçta yoktur; bunlar ancak GİB sisteminde bilinir.
- e-Arşiv **raporu** (`eArsivRaporu`) ve e-Defter kapsam dışıdır (sonraki sürüm).
- "Geçerli" = GİB'in yayımladığı XSD ve şematronu geçer; GİB'in sistem tarafındaki ek kontrolleri için garanti değildir.

## Kaynaklar

Paketler, sürümler, şematrona yapılan düzleştirme müdahaleleri ve GİB paketinde bulunan tutarsızlıklar: [KAYNAKLAR.md](KAYNAKLAR.md). Değişiklikler: [CHANGELOG.md](CHANGELOG.md).

MIT lisansı. GİB ile bir bağı yoktur; "GİB", "e-Fatura", "UBL-TR" ilgili kurumların adlarıdır.
