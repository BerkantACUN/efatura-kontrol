# efatura-kontrol — plan ve algoritma (21 Eylül 2026)

GİB'in UBL-TR e-belgelerini (e-Fatura, e-Arşiv Fatura, e-İrsaliye, uygulama yanıtı, zarf) GİB'e göndermeden önce **GİB'in kendi kurallarıyla** kontrol eden, hatayı Türkçe açıklayan ve nasıl düzeltileceğini söyleyen araç. CLI + Python kütüphanesi + MCP sunucusu. Tek repo, PyPI adı `efatura-kontrol` (boş, doğrulandı).

## 1. Araştırma sonuçları (doğrulanmış)

| Konu | Bulgu |
|---|---|
| Kaynak paketler | `UBL-TR1.2.1_Paketi.zip` (OASIS UBL 2.1 runtime XSD'leri + 49 örnek XML + görüntüleme XSLT'leri), `e-FaturaPaketi (29).zip` (GİB şematronu 3 dosya + zarf XSD'leri + WSDL), `earsiv_paket_v1.1_8.zip` (yalnız e-Arşiv **Raporu** XSD + XSLT-1.0 şematron). Hepsi ebelge.gib.gov.tr'den, anahtarsız. |
| Şematron dili | ISO Schematron, **XPath 2.0** kullanıyor (`matches`, `xs:date`, `castable as`, `exists`, `current-date`). `sch:include href="dosya#id"` parça-içerme, 133 soyut kural + `sch:extends`, kod listeleri şema seviyesinde 48 `let` değişkeni (ProfileID, InvoiceTypeCode, TaxType, Currency, Unit, …). e-Arşiv faturası aynı şematron, `type='earchive'` parametresiyle. |
| Motor seçimi | lxml (XSLT 1.0) çalışmaz. **pyschematron** parça-içermeyi ve soyut kuralları desteklemiyor, düzeltince bile belge başına ~2 s. **SaxonC-HE 13 (`saxonche`) + SchXslt2 1.5**: şematronu XSLT 3.0'a bir kez çevir (0,08 s), derle (0,17 s), belge başına **2–18 ms**, 27 kural ateşleniyor, sonuçlar GİB örnekleriyle tutarlı. Bedel: 40 MB wheel. Karar: saxonche. |
| Ön işleme şart | SchXslt2 soyut kuralı yalnız aynı örüntüde arıyor → derlemeden önce **düzleştirme**: include'ları göm, soyut kuralları `extends` yerine kopyala, kod-listesi `let`'lerini şema seviyesine taşı, eksik `xs` ad alanını ekle, `queryBinding="xslt2"` yaz. Deneme betiği çalıştı: 121 kural, 498 assert, 48 let. |
| XSD | lxml/libxml2 ile `UBL-Invoice-2.1.xsd` yükleme 0,1 s, belge başına **< 1 ms** (244 KB HKS örneği 0,7 ms). GİB'in kendi HKS örnekleri boş `ext:ExtensionContent` yüzünden XSD'den geçmiyor (README'ye not). |
| GİB'in eski örnekleri | e-FaturaPaketi içindeki örnekler UBL 2.0 / TR1.0 — şematron doğru şekilde reddediyor; testte "geçmesi beklenen" olarak kullanılmayacak. UBL-TR 1.2.1 örnekleri geçiyor (biri kasıtlı ID biçimi hatası içeriyor). |
| Kod listeleri | Şematrondaki `let`'ler makinece okunur ve GİB'in **fiilen** uyguladığı liste; PDF kılavuz (v1.42, Mart 2026) sadece açıklama için. Açıklamalar elle küçük bir JSON'a. |
| Güncelleme ritmi | GİB paketi yılda 4–6 kez güncelliyor (son: 14.09.2026 yürürlük). Paketten türetilen her şey betikle yeniden üretilecek; sürüm/tarih KAYNAKLAR.md'de. |

## 2. Kapsam

**v0.1 (ilk yayın)**
- Belge türleri: Invoice (e-Fatura tüm senaryolar + e-Arşiv), DespatchAdvice (e-İrsaliye), ReceiptAdvice, ApplicationResponse, StandardBusinessDocument (zarf).
- Katmanlar: (1) iyi biçimli XML, (2) XSD, (3) GİB şematronu, (4) aritmetik tutarlılık (satır/vergi/toplam), (5) imza **varlık ve yapı** kontrolü (kriptografik doğrulama yok, açıkça söylenir).
- Çıktı: Bulgu listesi (kod, seviye, mesaj, GİB'in özgün mesajı, konum XPath + satır no, açıklama, düzeltme önerisi), özet, JSON.
- CLI: `dogrula`, `ozet`, `kod`, `toplu`, `mcp`. MCP: 5 salt-okur araç.

**Sonraya:** örnek fatura üretici, e-Arşiv Raporu kontrolü (XSLT 1.0 → lxml ile ücretsiz), XAdES imza doğrulama, GİB "kullanıcı listesi" (etiket) kontrolü.

## 3. Mimari

```
efatura_kontrol/
  __init__.py        SURUM, PAKET_TARIHI
  bulgu.py           Bulgu, Rapor (dataclass, slots, frozen)
  belge.py           XML yükleme, tür tespiti (kök eleman + ProfileID), satır numaraları
  xsd.py             XSD kayıt: tür → derlenmiş XMLSchema (tembel, süreç ömrü boyunca tek)
  sematron.py        Saxon süreci + derlenmiş XSLT (tek örnek), SVRL → Bulgu
  hesap.py           aritmetik kontroller (Decimal, ROUND_HALF_UP)
  imza.py            ds:Signature / XAdES yapı kontrolü
  kod.py             kod listeleri (ekler/kodlar.json) + açıklama
  acikla.py          bulgu → Türkçe açıklama + düzeltme (ekler/aciklamalar.json)
  kontrol.py         boru hattı: belge → [xsd, sematron, hesap, imza] → Rapor
  toplu.py           klasör/çoklu dosya, ProcessPool (işçi başına bir Saxon)
  cli.py             argparse, utf-8 stdout, çıkış kodu
  mcp_server.py      MCPServer, 5 araç, SALT_OKUR açıklamaları
  ekler/
    xsd/             UBL 2.1 runtime XSD'leri (maindoc + common) + zarf XSD'leri
    sematron/efatura.sch   düzleştirilmiş GİB şematronu
    sematron/efatura.xsl   SchXslt2 çıktısı (derleme zamanında üretilir, repoya konur)
    kodlar.json      let'lerden türetilen kod listeleri (+ açıklamalar)
    aciklamalar.json assert → {kod, baslik, aciklama, duzeltme}
  araclar/
    paket_indir.py   GİB paketlerini indir, sha256 yaz
    duzlestir.py     şematron düzleştirme (bugünkü deneme betiğinin temizi)
    derle.py         SchXslt2 ile .sch → .xsl, kodlar.json üret
tests/               25+ test: GİB örnekleri (geçmesi/geçmemesi gerekenler), bozulmuş örnekler, hesap, CLI, MCP
```

## 4. Algoritma (boru hattı)

```
girdi: yol|bytes, tur=auto|efatura|earsiv|irsaliye|yanit|zarf
1. yükle: lxml parse (huge_tree=False, resolve_entities=False, no_network=True) → başarısızsa tek Bulgu "xml-bicim" (hata) ve dur
2. tür tespiti: kök QName → {Invoice, DespatchAdvice, ReceiptAdvice, ApplicationResponse, StandardBusinessDocument};
   Invoice ise ProfileID='EARSIVFATURA' → earsiv; tur parametresi verilmişse onunla çakışıyorsa "tur-uyumsuz" (uyarı)
3. xsd: türe göre şema.validate(doc); her error_log satırı → Bulgu(kaynak=xsd, seviye=hata, konum=path, satir=line)
   XSD hatası varsa şematrona yine de gir (GİB de öyle yapar, kullanıcı tüm listeyi görsün) — ama "yapısal hata varken şematron sonuçları eksik olabilir" bilgi bulgusu ekle
4. sematron: Saxon'a bytes ver; param type=earchive|efatura; SVRL al → failed-assert/successful-report → Bulgu(kaynak=sematron, kural=@id|@test, konum=@location, mesaj=svrl:text)
   konum XPath'i lxml ile çözülüp satır numarası bulunur (tek sefer, dict önbellek)
5. hesap (yalnız Invoice/DespatchAdvice değil, Invoice):
   satır: LineExtensionAmount ≈ InvoicedQuantity × Price/PriceAmount (− AllowanceCharge[ChargeIndicator=false] + [true]); tolerans 0,01
   vergi alt toplamı: TaxAmount ≈ TaxableAmount × Percent/100 (kuruşa yuvarla); TaxTotal.TaxAmount = Σ TaxSubtotal
   dip: TaxExclusiveAmount ≈ Σ satır ext − belge indirim + belge artırım; TaxInclusiveAmount ≈ TaxExclusive + Σ vergi;
        PayableAmount ≈ TaxInclusive − WithholdingTaxTotal + PayableRoundingAmount; AllowanceTotalAmount = Σ indirim
   para birimi: tüm currencyID'ler DocumentCurrencyCode ile aynı mı; TRY değilse PricingExchangeRate zorunlu (şematron da bakar, hesap CalculationRate ile TRY karşılığını raporlar)
   tevkifat: WithholdingTaxTotal.TaxAmount ≈ Σ TaxSubtotal ve oranlar kod listesindeki oranla (örn. 627 = 5/10) uyumlu mu
   → seviye uyarı (GİB matematiği reddetmez ama alıcı reddeder)
6. imza: ext:UBLExtensions//ds:Signature var mı, ds:Reference URI'leri belge içinde çözülüyor mu, xades:SigningTime var mı, X509 var mı → yoksa "imza-yok" (bilgi: imzasız taslak olabilir)
7. Rapor: bulgular kaynak→seviye→satır sırasında; özet {hata, uyari, bilgi, tur, profil, faturaTipi, sure_ms, paket_tarihi}
çıkış kodu: hata>0 → 1
```

Toplu mod: dosya listesi → `ProcessPoolExecutor(max_workers=cpu)`; her işçi ilk çağrıda kendi Saxon+XSD'sini kurar (initializer), sonuç JSONL akış; 1.000 fatura ≈ cpu×… hedef: 8 çekirdekte < 30 s.

## 5. Veri modeli

```
Bulgu(kod, seviye: hata|uyari|bilgi, kaynak: xml|xsd|sematron|hesap|imza,
      mesaj, gib_mesaj|None, kural|None, konum|None, satir|None, deger|None,
      aciklama|None, duzeltme|None)
Rapor(dosya, tur, profil, tip, bulgular: tuple[Bulgu,...], sure_ms, paket)
  .hata_sayisi .uyari_sayisi .gecerli  .json()  .metin()
```
Bulgu kodları: `xml-bicim`, `xsd-<kısa>`, `sch-<assert id ya da kural adı>` (GİB id vermiyorsa düzleştirmede biz `KuralAdi-n` id'si basarız), `hesap-satir`, `hesap-kdv`, `hesap-dip`, `hesap-tevkifat`, `hesap-kur`, `imza-yok`, `imza-yapi`.

## 6. Performans kuralları
- Saxon süreci ve derlenmiş XSLT süreç ömrü boyunca tek (`functools.lru_cache`/modül tekil); MCP'de ilk çağrıda ısınır.
- XSD şemaları tür başına bir kez; `etree.XMLParser` tekil, `remove_blank_text=False` (satır numaraları korunur).
- Belge bir kez parse edilir; Saxon'a lxml'den `tostring` değil **ham bytes** verilir (ikinci parse Saxon'da kaçınılmaz, 1–5 ms).
- SVRL: `transform_to_string` + tek lxml parse; failed-assert dışındaki düğümler atlanır.
- Hesap: `Decimal` ile, `quantize(Decimal("0.01"), ROUND_HALF_UP)`, XPath'ler modül seviyesinde `etree.XPath` olarak derli.
- Toplu: süreç havuzu; büyük dosyalar önce (uzun kuyruk azalır).
- Bellek: `huge_tree=False`, 50 MB üstü dosya reddedilir (bulgu ile).
- Yorum satırı yok; isimler Türkçe ve açıklayıcı (ifc-ruhsat üslubu).

## 7. Test stratejisi
- GİB UBL-TR 1.2.1 örnekleri: XSD geçmeli; şematronda beklenen sonuçlar sabitlenir (TemelFaturaOrnegi → `sch-InvoiceIDCheck` bekleniyor).
- Bozma testleri: geçerli örnekten türetilmiş 15 bozuk kopya (yanlış ProfileID, TCKN 10 hane, KDV %20 yerine 21, toplam uyuşmazlığı, TRY dışı kursuz, tarih ileri, UUID bozuk, unitCode eksik, tevkifat oranı yanlış…).
- Hesap testleri: elle hesaplanmış küçük faturalar.
- Zarf testi, irsaliye testi, e-Arşiv `type` testi.
- CLI/JSON/çıkış kodu; MCP araç listesi ve çağrı.
- Tazelik testi: `ekler/sematron/efatura.xsl` düzleştirilmiş .sch'den yeniden üretildiğinde aynı mı (ifc-ruhsat'taki IDS-tazelik gibi).
- CI: ubuntu/windows × py3.10/3.12; saxonche her ikisinde wheel var.

## 8. Adım adım kodlama sırası
1. Proje iskeleti: pyproject (hatchling, bağımlılık lxml + saxonche, `mcp` isteğe bağlı), `__init__`, ruff, CI, LICENSE (MIT), `araclar/paket_indir.py` (+ sha256, KAYNAKLAR.md).
2. `araclar/duzlestir.py` + `araclar/derle.py` → `ekler/sematron/efatura.sch`, `efatura.xsl`, `ekler/kodlar.json`; `ekler/xsd/` kopyası.
3. `bulgu.py`, `belge.py` (yükleme + tür tespiti + satır no) — testleriyle.
4. `xsd.py` — testleriyle.
5. `sematron.py` (Saxon tekil, param `type`, SVRL→Bulgu, konum→satır) — testleriyle.
6. `hesap.py` — testleriyle (Decimal).
7. `imza.py`, `kod.py`, `acikla.py` (+ `ekler/aciklamalar.json` ilk 40 açıklama).
8. `kontrol.py` boru hattı + `toplu.py` — uçtan uca testler, performans ölçümü README'ye.
9. `cli.py` — testleri.
10. `mcp_server.py` — testleri; `server.json`.
11. README (Türkçe; kurulum `uvx efatura-kontrol`, örnek çıktı, sınırlar, GİB örneklerinde sonuç tablosu), KAYNAKLAR.md, CHANGELOG, tazelik CI adımı.
12. Yayın: PyPI (trusted publishing, `publish.yaml`), MCP kayıt defteri, Glama claim, awesome-mcp-servers PR (Finance), LinkedIn yazısı.

## 9. Açık noktalar (kodlarken karar)
- saxonche ilk import ~0,3 s; CLI'da `ozet`/`kod` komutları Saxon'u hiç yüklemesin (tembel import).
- GİB assert'lerinin id'si yok: düzleştirmede her assert'e `KuralAdi-<sıra>` id'si basılır; açıklama JSON'u bu id'lere bağlanır. GİB kuralı güncellerse id kayar → tazelik testi yakalar, açıklama eşlemesi test ile doğrulanır (mesaj metni hash'i ile).
- `type` parametresi SchXslt2 çıktısında `xsl:param` olarak çıkıyor (doğrulandı) → e-Arşiv için `set_parameter("type","earchive")`.
- HKS/İDİS gibi çok büyük örnekler (250 KB) için hesap modülü satır sayısına göre O(n) kalmalı; XPath'ler tek geçiş.
