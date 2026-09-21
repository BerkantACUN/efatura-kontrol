from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

Seviye = Literal["hata", "uyari", "bilgi"]
Kaynak = Literal["xml", "xsd", "sematron", "hesap", "imza"]
SIRA = {"hata": 0, "uyari": 1, "bilgi": 2}


@dataclass(frozen=True, slots=True)
class Bulgu:
    kod: str
    seviye: Seviye
    kaynak: Kaynak
    mesaj: str
    gib_mesaj: str | None = None
    kural: str | None = None
    konum: str | None = None
    satir: int | None = None
    deger: str | None = None
    aciklama: str | None = None
    duzeltme: str | None = None

    def sozluk(self) -> dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}


@dataclass(slots=True)
class Rapor:
    dosya: str
    tur: str | None
    profil: str | None = None
    tip: str | None = None
    bulgular: list[Bulgu] = field(default_factory=list)
    sure_ms: float = 0.0
    paket: dict[str, str] = field(default_factory=dict)

    def ekle(self, *bulgular: Bulgu) -> None:
        self.bulgular.extend(bulgular)

    def sirala(self) -> None:
        self.bulgular.sort(key=lambda b: (SIRA[b.seviye], b.satir or 0, b.kod))

    def sayim(self, seviye: Seviye) -> int:
        return sum(1 for b in self.bulgular if b.seviye == seviye)

    @property
    def gecerli(self) -> bool:
        return self.sayim("hata") == 0

    def ozet(self) -> dict[str, Any]:
        return {
            "gecerli": self.gecerli,
            "hata": self.sayim("hata"),
            "uyari": self.sayim("uyari"),
            "bilgi": self.sayim("bilgi"),
            "tur": self.tur,
            "profil": self.profil,
            "tip": self.tip,
            "sure_ms": round(self.sure_ms, 1),
        }

    def sozluk(self) -> dict[str, Any]:
        return {
            "dosya": self.dosya,
            "ozet": self.ozet(),
            "paket": self.paket,
            "bulgular": [b.sozluk() for b in self.bulgular],
        }

    def metin(self) -> str:
        o = self.ozet()
        durum = "GEÇERLİ" if self.gecerli else "GEÇERSİZ"
        satirlar = [
            f"{self.dosya}: {durum} — {o['hata']} hata, {o['uyari']} uyarı, {o['bilgi']} bilgi "
            f"({o['tur'] or '?'}{' / ' + o['profil'] if o['profil'] else ''}"
            f"{' / ' + o['tip'] if o['tip'] else ''}, {o['sure_ms']} ms)"
        ]
        for b in self.bulgular:
            yer = f" [satır {b.satir}]" if b.satir else ""
            satirlar.append(f"  {b.seviye.upper():5} {b.kod}{yer}: {b.mesaj}")
            if b.duzeltme:
                satirlar.append(f"        → {b.duzeltme}")
        return "\n".join(satirlar)
