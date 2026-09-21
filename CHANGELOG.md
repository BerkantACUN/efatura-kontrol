# Değişiklikler

## [0.1.0] — 2026-09-21

İlk yayın.

- GİB e-Fatura Paketi (29) şematronu düzleştirilip SchXslt2 ile XSLT 3.0'a derlendi, SaxonC-HE ile çalışıyor: 121 kural, 499 assert, 41 kod listesi; e-Fatura, e-Arşiv (`type=earchive`), e-İrsaliye, irsaliye/uygulama yanıtı ve zarf.
- OASIS UBL 2.1 XSD (UBL-TR 1.2.1 paketi) + GİB zarf/HRXML şemaları.
- Aritmetik kontroller (satır, vergi, tevkifat, dip toplamlar, currencyID), imza yapısı kontrolü.
- Bulgu: kod, seviye, GİB mesajı, kural, XPath konumu, satır numarası, Türkçe açıklama ve düzeltme (65 hazır açıklama).
- CLI (`dogrula`, `ozet`, `kod`, `acikla`, `toplu`, `mcp`, `derle`), MCP sunucusu (5 salt-okur araç), Python API.
- `ornekler/`: dört tam geçerli belge ve bir hatalı örnek; 48 test, %92 kapsam; CI güncel GİB paketiyle tazelik denetimi yapıyor.
