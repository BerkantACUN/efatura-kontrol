# efatura-kontrol — kurulum rehberi (Cline ve diğer yapay zekâ ajanları için)

Bu dosya, bir yapay zekâ ajanının (Cline vb.) efatura-kontrol MCP sunucusunu kullanıcıya soru sormadan kurabilmesi için yazıldı. *This file lets an AI agent such as Cline install the efatura-kontrol MCP server on its own; the steps are in Turkish, commands and JSON are copy-paste ready.*

efatura-kontrol, GİB UBL-TR e-belgelerini (e-Fatura, e-Arşiv fatura, e-İrsaliye, uygulama yanıtı, zarf) GİB'in kendi XSD ve şematron kurallarıyla yerelde denetler. Beş salt-okur araç sunar. API anahtarı, hesap ya da ortam değişkeni **gerekmez**; belgeler ağa gönderilmez.

## 1. Ön koşul: uv

Sunucu PyPI'deki `efatura-kontrol` paketinden `uvx` ile çalışır; Python 3.10+ ve bağımlılıkları (lxml, SaxonC-HE) uv kendisi getirir. `uvx --version` çalışmıyorsa uv'yi kurun:

- macOS / Linux: `curl -LsSf https://astral.sh/uv/install.sh | sh`
- Windows (PowerShell): `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`

Kurulumdan sonra yeni bir terminal açın ya da uv'nin yazdığı PATH talimatını uygulayın. uv kurulamıyorsa yedek yol: `pip install efatura-kontrol`, ardından aşağıdaki yapılandırmada `"command": "efatura-kontrol", "args": ["mcp"]`.

## 2. Paketi önceden indirin (önerilir)

İlk çalıştırmada SaxonC-HE tekerleği (~40 MB) iner. MCP istemcisi zaman aşımına düşmesin diye bir kez elle çalıştırın:

```bash
uvx efatura-kontrol --version
```

Çıktı `efatura-kontrol 0.x.y` olmalı.

## 3. MCP yapılandırması

Cline'ın `cline_mcp_settings.json` dosyasındaki `mcpServers` nesnesine ekleyin:

```json
{
  "mcpServers": {
    "efatura-kontrol": {
      "command": "uvx",
      "args": ["efatura-kontrol", "mcp"],
      "disabled": false,
      "autoApprove": [
        "belge_dogrula",
        "belge_ozeti",
        "bulgu_acikla",
        "kod_listesi",
        "kod_listeleri"
      ]
    }
  }
}
```

Bütün araçlar salt okurdur (dosya yazmaz, silmez, ağa çıkmaz); bu yüzden `autoApprove` güvenlidir. Kullanıcı her çağrıyı onaylamak isterse listeyi boş bırakın.

Windows'ta `uvx` PATH'te bulunamazsa `"command"` alanına tam yolu yazın (ör. `C:\\Users\\<ad>\\.local\\bin\\uvx.exe`).

### Uzak sunucu (isteğe bağlı)

Kullanıcı kendi barındırdığı bir sunucunun adresini verdiyse (README, "Uzak sunucu (Docker)"), yerel komut yerine:

```json
{
  "mcpServers": {
    "efatura-kontrol": {
      "type": "streamableHttp",
      "url": "https://<sunucu>/mcp",
      "headers": { "X-API-Key": "<anahtar>" }
    }
  }
}
```

Uzak sunucuda `dosya` parametresi güvenlik gereği kapalıdır (sunucu kendi diskini okumaz). Belgeyi `xml` parametresiyle, dosyanın metni olarak gönderin.

## 4. Doğrulama

Sunucu listede etkin görünmeli ve beş araç sunmalı. Belge gerektirmeyen araçlarla deneyin:

- `kod_listeleri` → `{}` : yanıttaki `paket.ublTr` alanı dolu olmalı (ör. `"1.2.1"`).
- `kod_listesi` → `{"liste": "UnitCodeList", "ara": "C62"}` : `degerler` = `["C62"]`.

Kullanıcının bir belgesi varsa: `belge_dogrula` → `{"dosya": "<tam yol>.xml"}` (yerel) ya da `{"xml": "<belge metni>"}`.

## Sorun giderme

| Belirti | Çözüm |
|---|---|
| `uvx: command not found` | 1. adım; ya da `command` alanına uvx'in tam yolu |
| İlk çağrıda zaman aşımı | 2. adımdaki `uvx efatura-kontrol --version` ile paketi önceden indirin |
| `dosya-yok` bulgusu | `dosya` mutlak yol olmalı |
| `uzak-dosya-kapali` hatası | Uzak sunucudasınız; belgeyi `xml` ile gönderin |
| Python sürüm hatası | uv kendi Python'unu indirir; `pip` yolu seçildiyse Python ≥ 3.10 gerekir |
