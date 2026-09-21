import hashlib
import sys
import urllib.request
import zipfile
from pathlib import Path

PAKETLER = {
    "UBL-TR1.2.1_Paketi.zip": "https://ebelge.gib.gov.tr/dosyalar/kilavuzlar/UBL-TR1.2.1_Paketi.zip",
    "e-FaturaPaketi.zip": "https://ebelge.gib.gov.tr/dosyalar/kilavuzlar/e-FaturaPaketi%20(29).zip",
    "earsiv_paket.zip": "https://ebelge.gib.gov.tr/dosyalar/kilavuzlar/earsiv_paket_v1.1_8.zip",
    "schxslt2.zip": "https://zenodo.org/records/16979335/files/schxslt2-1.5.zip?download=1",
}


def indir(hedef: Path) -> dict[str, str]:
    hedef.mkdir(parents=True, exist_ok=True)
    ozetler = {}
    for ad, url in PAKETLER.items():
        yol = hedef / ad
        if not yol.exists():
            istek = urllib.request.Request(
                url, headers={"User-Agent": "efatura-kontrol/paket_indir"}
            )
            with urllib.request.urlopen(istek, timeout=120) as r:
                yol.write_bytes(r.read())
        ozetler[ad] = hashlib.sha256(yol.read_bytes()).hexdigest()
        with zipfile.ZipFile(yol) as z:
            z.extractall(hedef / ad.removesuffix(".zip"))
    return ozetler


def main(argv: list[str] | None = None) -> int:
    hedef = Path((argv or sys.argv[1:] or ["kaynak"])[0])
    for ad, ozet in indir(hedef).items():
        print(f"{ozet}  {ad}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
