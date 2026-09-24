# Değişiklikler

## [Unreleased]

### Changed

- README: ayrıntılı İngilizce bölüm (kurulum, komutlar, sonucu okuma, yerel MCP, uzak sunucu/Docker, Python API, sınırlar).
- Bağımlılık alt sınırı `mcp>=2.0` (kod MCPServer API'sini kullanıyor; 1.x ile hiç yüklenmiyordu).
- MCP araç tanımları yeniden yazıldı: ne yaptığı, ne zaman kullanılacağı, girdi örnekleri ve dönüş biçimi; her parametrenin şemada açıklaması ve örnekleri; her araçta başlık ve eksiksiz ToolAnnotations (`readOnlyHint`, `destructiveHint: false`, `idempotentHint`, `openWorldHint: false`).

### Added

- 118 şematron kuralına Türkçe açıklama ve düzeltme önerisi: e-Fatura, e-İrsaliye ve irsaliye yanıtı kurallarının tamamı açıklamalı; toplam kapsam %14,8 → %54,5 (297 kuraldan 162). `araclar/sematron_kapsam.py` kapsamı ve mutasyon taramasıyla tetiklenme sıklığını raporlar.
- `efatura-kontrol mcp --http`: MCP Python SDK'nın streamable HTTP taşımasıyla uzak sunucu (yol `/mcp`, durumsuz). Adres/port `--host`/`--port` ya da `EFATURA_HOST`/`EFATURA_PORT` (varsayılan `0.0.0.0:8080`); `EFATURA_API_KEY` verilirse `X-API-Key` başlığı zorunlu; anahtar yoksa açılışta uyarı basılır. Uzak modda `dosya` parametresi kapalı (sunucu diskinden okuma yok), istek gövdesi 64 MB ile sınırlı.
- `ornek-fatura` komutu ve `ornek_fatura` MCP aracı: taraflar, satırlar ve KDV oranından geçerli, imzasız UBL-TR 1.2 SATIS faturası (TEMELFATURA / TICARIFATURA / EARSIVFATURA, TRY); üretilen belge kendi doğrulamasından hatasız geçer.
- `llms-install.md`: Cline gibi ajanların sunucuyu kendi başına kurması için adım adım rehber (uv, yapılandırma, doğrulama, sorun giderme).
- Dockerfile (Python 3.12 slim, çok aşamalı, root olmayan kullanıcı) ve `ghcr.io/berkantacun/efatura-kontrol` imajını `v*` etiketlerinde yayınlayan Docker iş akışı.

### Fixed

- Alt komut verilmeden çalıştırıldığında (stdin bir boruysa) doğrudan MCP sunucusu olarak başlar: bazı MCP barındırıcıları ve dizin derleyicileri paketi `efatura-kontrol` diye çağırıyor. Terminalde davranış değişmedi, yardım basılır.

## [0.1.0] — 2026-09-21

İlk yayın.

- GİB e-Fatura Paketi (29) şematronu düzleştirilip SchXslt2 ile XSLT 3.0'a derlendi, SaxonC-HE ile çalışıyor: 121 kural, 499 assert, 41 kod listesi; e-Fatura, e-Arşiv (`type=earchive`), e-İrsaliye, irsaliye/uygulama yanıtı ve zarf.
- OASIS UBL 2.1 XSD (UBL-TR 1.2.1 paketi) + GİB zarf/HRXML şemaları.
- Aritmetik kontroller (satır, vergi, tevkifat, dip toplamlar, currencyID), imza yapısı kontrolü.
- Bulgu: kod, seviye, GİB mesajı, kural, XPath konumu, satır numarası, Türkçe açıklama ve düzeltme (65 hazır açıklama).
- CLI (`dogrula`, `ozet`, `kod`, `acikla`, `toplu`, `mcp`, `derle`), MCP sunucusu (5 salt-okur araç), Python API.
- `ornekler/`: dört tam geçerli belge ve bir hatalı örnek; 48 test, %92 kapsam; CI güncel GİB paketiyle tazelik denetimi yapıyor.
