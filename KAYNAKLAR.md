# Kaynaklar ve türetme

Bu araçtaki hiçbir kural elle yazılmış bir "GİB böyle ister" yorumu değildir; XSD'ler OASIS'in, şematron ve kod listeleri GİB'in yayımladığı dosyalardan betikle türetilir. Elle yazılan tek şey Türkçe açıklamalar (`ekler/aciklamalar.json`) ve aritmetik kontrollerdir (`hesap.py`, UBL-TR 1.2.1 Fatura Kılavuzu'ndaki tanımlara göre).

## İndirilen paketler (21 Eylül 2026)

| Paket | URL | sha256 |
|---|---|---|
| UBL-TR 1.2.1 Paketi | https://ebelge.gib.gov.tr/dosyalar/kilavuzlar/UBL-TR1.2.1_Paketi.zip | `cb583941b8a8a239c59902c6bc455c0f75d48f2bb81d7d3fbe1ae827f981f7db` |
| e-Fatura Paketi (29) | https://ebelge.gib.gov.tr/dosyalar/kilavuzlar/e-FaturaPaketi%20(29).zip | `12901476cd424fd65c779a4fb44cee798f9921ce55b003f8a076c936ddf8b583` |
| e-Arşiv Paketi v1.1_8 (rapor XSD, henüz kullanılmıyor) | https://ebelge.gib.gov.tr/dosyalar/kilavuzlar/earsiv_paket_v1.1_8.zip | `97a6f70564a21bd68bd024c83b3d85a530e4e45cb3dbd9c986942b1b01b48b6d` |
| SchXslt2 1.5 (şematron → XSLT 3.0 çevirici, MIT) | https://zenodo.org/records/16979335 | `667055df08afc8f8c24027c21aab162a10ae7e044493da9970fd997cda1e5d21` |

Duyuru sayfası: https://ebelge.gib.gov.tr/duyurular.html — son güncelleme duyurusu 14.09.2026 yürürlük tarihli; şematron `History.txt` son kaydı 20260701. UBL-TR Kod Listeleri Kılavuzu v1.42 (Mart 2026) yalnız açıklama metinleri için okundu; uygulanan liste şematrondaki `let` değişkenleridir.

## Ne, nereden

| Çıktı | Kaynak | Betik |
|---|---|---|
| `ekler/xsd/common`, `ekler/xsd/maindoc` | UBL-TR paketi `xsdrt/` (OASIS UBL 2.1 runtime XSD) | `derle._xsd_kopyala` |
| `ekler/xsd/zarf`, `ekler/xsd/HRXML` | e-Fatura Paketi `xsd/Envelope`, `xsd/HRXML`; `Package_1_2.xsd` içindeki `schemaLocation` yolları `../maindoc/` olarak düzeltildi | aynı |
| `ekler/sematron/efatura.sch` | `UBL-TR_Main_Schematron.xml` + `UBL-TR_Common_Schematron.xml#abstracts` + `UBL-TR_Codelist.xml#codes` | `derle.duzlestir` |
| `ekler/sematron/efatura.xsl` | düzleştirilmiş şematron → SchXslt2 | `derle.cevir` |
| `ekler/kodlar.json` | şematrondaki `',A,B,C,'` biçimli `let` değişkenleri | `derle.kod_listeleri` |

## Şematrona yapılan müdahaleler (düzleştirme)

GİB'in şematronu ISO Schematron'un eski "skeleton" uygulamasına göre yazılmış; standarda tam uyan bir motorda olduğu gibi çalışmaz. `derle.duzlestir` şunları yapar, hepsi anlam korunarak:

1. `sch:include href="dosya#id"` parça-içermeleri belgenin içine gömülür.
2. Şema seviyesinde duran 9 "genel" kural (`//cbc:IssueDate`, `//@unitCode`, `//@currencyID`, `//cbc:IdentificationCode`…) standartta bir örüntü içinde olmak zorundadır; `genel` adlı örüntüye alınır. GİB bu kuralları fiilen uygular (birim kodu hataları bu kurallardan gelir).
3. 133 soyut kural (`abstract="true"`) `sch:extends` ile kullanıldığı her kuralın içine kopyalanır; SchXslt2 soyut kuralı yalnız aynı örüntüde arar.
4. Kod listesi `let`'leri (`codes` örüntüsü) şema seviyesine taşınır; eski skeleton bunları küresel değişken yapıyordu.
5. GİB `xs:` önekini bildirmeden kullanır; `xs` ad alanı eklenir. `queryBinding="xslt2"` yazılır.
6. Her `assert`'e kararlı bir `id` verilir: soyut kuraldakine `KuralAdı-n`, doğrudan olanlara `örüntü-kural-n`.
7. `xs:date(.)` içeren iki tarih kuralı (`TimeCheck-1/2`) `. castable as xs:date` korumasına alınır ve önlerine `TarihBicimi-1` adlı ayrı bir biçim kontrolü eklenir; aksi halde geçersiz bir tarih dinamik hata verip belgenin geri kalanının denetimini yutuyordu.
8. SchXslt2 şu ayarlarla çalıştırılır: dinamik hatada durma kapalı (hata `svrl:error` olarak rapora düşer, `sch-degerlendirme` bulgusu olur), `fired-rule` ve `active-pattern` raporlaması kapalı (hız), üretilen XSLT `version="1.0"` uyumluluk kipinde (GİB kuralları `string(cbc:FirstName)` gibi XPath 1.0 alışkanlıkları içeriyor; 2.0 kipinde iki `FirstName` görünce hata veriyordu).

`type` parametresi (`efatura` | `earchive` | `goruntuleme`) SchXslt2 çıktısında `xsl:param` olarak kalır; e-Arşiv faturaları için çalışma zamanında `earchive` verilir.

## GİB paketinde görülen tutarsızlıklar

- UBL-TR 1.2.1 örneklerinin çoğu bugünkü şematrondan geçmez: `TemelFaturaOrnegi` (ID biçimi, 10 haneli TCKN), `TEVKIFAT`/`ISTISNA-2`/`HASTANE` (`unitCode` yok), `IadeFaturasiOrnegi` (TICARIFATURA'da IADE), `IHRACAT` (imza yapısı eksik).
- `HKS-Ornek1/2` boş `<ext:ExtensionContent/>` içerdiğinden UBL 2.1 XSD'sinden geçmez.
- `HKS-Ornek2` belge düzeyinde `ChargeIndicator=false` (indirim) yazıp dip toplamda bunları `ChargeTotalAmount` (artırım) olarak toplar; HKS için dip aritmetiği bu yüzden kontrol edilmez.
- e-Fatura Paketi'ndeki `xml/` örnekleri UBL 2.0 / TR1.0 sürümündedir (2013); `7_UYGULAMA_YANITI_IADE.xml` iyi biçimli XML bile değildir.
- `Açıklamalar.txt` ve `History.txt` Windows-1254 kodludur.

## Aritmetik kuralların dayanağı

UBL-TR 1.2.1 Fatura Kılavuzu, "Toplamlar" (`cac:LegalMonetaryTotal`) ve "Vergi" (`cac:TaxTotal`, `cac:WithholdingTaxTotal`) bölümleri; tevkifatlı fatura örneği (`TEVKIFAT.xml`): `TaxTotal/TaxAmount` = KDV − tevkifat, `TaxInclusiveAmount` = vergi hariç + tam KDV, `PayableAmount` = vergiler dahil − tevkifat. Tolerans 0,01; yuvarlama kuruşa, yarım yukarı.
