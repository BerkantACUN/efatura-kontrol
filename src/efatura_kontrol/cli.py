from __future__ import annotations

import argparse
import contextlib
import json
import os
import sys

from efatura_kontrol import PAKET, SURUM
from efatura_kontrol.belge import TURLER


def _yaz(veri) -> None:
    print(json.dumps(veri, ensure_ascii=False, indent=2))


def _komutlari_coz(argv: list[str] | None) -> list[str]:
    """Argümansız çağrı: uçta bir MCP istemcisi varsa (stdin boru) sunucuyu başlat.
    Bazı MCP barındırıcıları ve dizin derleyicileri paketi alt komut vermeden
    çalıştırıyor; insan terminalinde davranış değişmez, yardım basılır."""
    verilen = list(sys.argv[1:] if argv is None else argv)
    if verilen:
        return verilen
    try:
        etkilesimli = sys.stdin.isatty()
    except (AttributeError, ValueError):
        etkilesimli = False
    return verilen if etkilesimli else ["mcp"]


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="efatura-kontrol",
        description=(
            "GİB UBL-TR e-belgelerini (e-Fatura, e-Arşiv, e-İrsaliye, zarf) GİB'in kendi XSD ve "
            f"şematron kurallarıyla kontrol eder (UBL-TR {PAKET['ublTr']}, e-Fatura Paketi "
            f"{PAKET['eFaturaPaketi']}, şematron {PAKET['sematronGuncelleme']})."
        ),
    )
    p.add_argument("--version", action="version", version=f"efatura-kontrol {SURUM}")
    alt = p.add_subparsers(dest="komut", required=True)

    d = alt.add_parser("dogrula", help="belgeyi denetle, bulguları yaz")
    d.add_argument("dosya", nargs="+")
    d.add_argument("--tur", choices=TURLER, help="belge türünü zorla (varsayılan: kök elemandan)")
    d.add_argument("--json", action="store_true", help="JSON çıktı")
    d.add_argument("--sessiz", action="store_true", help="yalnız özet satırı")

    o = alt.add_parser("ozet", help="belgenin kimliği: senaryo, tip, taraflar, satırlar, toplamlar")
    o.add_argument("dosya")

    k = alt.add_parser(
        "kod", help="GİB kod listesi: `kod` (liste adları), `kod UnitCodeList --ara KGM`"
    )
    k.add_argument("liste", nargs="?")
    k.add_argument("--ara")

    a = alt.add_parser("acikla", help="bir bulgu kodunun Türkçe açıklaması ve düzeltmesi")
    a.add_argument("kod")

    t = alt.add_parser("toplu", help="klasör ya da dosya listesini paralel denetle (JSONL)")
    t.add_argument("yol", nargs="+")
    t.add_argument("--isci", type=int, help="süreç sayısı (varsayılan: çekirdek sayısı)")
    t.add_argument("--json", action="store_true", help="satır başına bir JSON rapor")

    of = alt.add_parser(
        "ornek-fatura",
        help="taraflar/satırlar JSON'undan geçerli, imzasız UBL-TR örnek fatura üret",
    )
    of.add_argument(
        "girdi",
        nargs="?",
        help="JSON girdi dosyası ya da - (stdin); verilmezse yerleşik örnek kullanılır",
    )
    of.add_argument("-o", "--cikti", help="XML'i bu dosyaya yaz (varsayılan: stdout)")
    of.add_argument(
        "--senaryo", choices=("TEMELFATURA", "TICARIFATURA", "EARSIVFATURA"), help="senaryoyu zorla"
    )

    m = alt.add_parser("mcp", help="MCP sunucusunu başlat (varsayılan stdio; --http ile uzak)")
    m.add_argument(
        "--http",
        action="store_true",
        help="streamable HTTP (yol /mcp); EFATURA_API_KEY varsa X-API-Key zorunlu",
    )
    m.add_argument("--host", help="dinlenecek adres (EFATURA_HOST, varsayılan 0.0.0.0)")
    m.add_argument("--port", type=int, help="port (EFATURA_PORT, varsayılan 8080)")

    dr = alt.add_parser("derle", help="GİB paketlerinden ekler/ üret (geliştirici)")
    dr.add_argument("kaynak", nargs="?", default="kaynak")
    dr.add_argument("hedef", nargs="?")

    args = p.parse_args(_komutlari_coz(argv))
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    try:
        return KOMUTLAR[args.komut](args)
    except BrokenPipeError:
        # Çıktıyı okuyan taraf kapandı (`| head` gibi): traceback basma, kalan yazımları yut
        with contextlib.suppress(OSError, ValueError):
            os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        return 141


def _dogrula(args) -> int:
    from efatura_kontrol.kontrol import hazirla, kontrol_et

    hazirla()
    hatali = False
    raporlar = []
    for dosya in args.dosya:
        rapor = kontrol_et(dosya, args.tur)
        hatali = hatali or not rapor.gecerli
        if args.json:
            raporlar.append(rapor.sozluk())
        elif args.sessiz:
            print(rapor.metin().splitlines()[0])
        else:
            print(rapor.metin())
    if args.json:
        _yaz(raporlar[0] if len(raporlar) == 1 else raporlar)
    return 1 if hatali else 0


def _ozet(args) -> int:
    from efatura_kontrol.belge import BelgeHatasi
    from efatura_kontrol.kontrol import ozet

    try:
        _yaz(ozet(args.dosya))
    except BelgeHatasi as e:
        print(f"{e.kod}: {e.mesaj}", file=sys.stderr)
        return 1
    return 0


def _kod(args) -> int:
    from efatura_kontrol import kod

    if not args.liste:
        _yaz(kod.liste_adlari())
        return 0
    try:
        _yaz(kod.liste(args.liste, args.ara))
    except KeyError as e:
        print(e.args[0], file=sys.stderr)
        return 1
    return 0


def _acikla(args) -> int:
    from efatura_kontrol import kod

    a = kod.acikla(args.kod)
    if a is None:
        print(f"{args.kod} için hazır açıklama yok; GİB mesajı bulguda verilir", file=sys.stderr)
        return 1
    _yaz({"kod": args.kod, **a})
    return 0


def _toplu(args) -> int:
    from efatura_kontrol.toplu import toplu_kontrol

    hatali = sayi = 0
    for rapor in toplu_kontrol(args.yol, args.isci):
        sayi += 1
        hatali += 0 if rapor.gecerli else 1
        print(
            json.dumps(rapor.sozluk(), ensure_ascii=False)
            if args.json
            else rapor.metin().splitlines()[0]
        )
    if not args.json:
        print(f"{sayi} belge, {hatali} geçersiz")
    return 1 if hatali else 0


def _mcp(args) -> int:
    from efatura_kontrol import mcp_server

    if getattr(args, "http", False):
        mcp_server.http_calistir(args.host, args.port)
    else:
        mcp_server.mcp.run()
    return 0


def _ornek_fatura(args) -> int:
    from pydantic import ValidationError

    from efatura_kontrol.kontrol import kontrol_et
    from efatura_kontrol.mcp_server import ORNEK_ALICI, ORNEK_SATICI, ORNEK_SATIR
    from efatura_kontrol.uret import ornek_fatura

    if args.girdi is None:
        veri = {"satici": ORNEK_SATICI, "alici": ORNEK_ALICI, "satirlar": [ORNEK_SATIR]}
    else:
        try:
            metin = (
                sys.stdin.read() if args.girdi == "-" else open(args.girdi, encoding="utf-8").read()  # noqa: SIM115
            )
            veri = json.loads(metin)
        except (OSError, json.JSONDecodeError) as e:
            print(f"girdi okunamadı: {e}", file=sys.stderr)
            return 2
    if args.senaryo:
        veri["senaryo"] = args.senaryo
    try:
        xml = ornek_fatura(veri)
    except ValidationError as e:
        print(f"girdi geçersiz:\n{e}", file=sys.stderr)
        return 2
    rapor = kontrol_et(xml.encode("utf-8"), None, args.cikti or "<ornek>")
    if args.cikti:
        with open(args.cikti, "w", encoding="utf-8", newline="\n") as f:
            f.write(xml)
    else:
        sys.stdout.write(xml)
    print(rapor.metin().splitlines()[0], file=sys.stderr)
    return 0 if rapor.gecerli else 1


def _derle(args) -> int:
    from efatura_kontrol import derle

    return derle.main([args.kaynak] + ([args.hedef] if args.hedef else []))


KOMUTLAR = {
    "dogrula": _dogrula,
    "ozet": _ozet,
    "kod": _kod,
    "acikla": _acikla,
    "toplu": _toplu,
    "ornek-fatura": _ornek_fatura,
    "mcp": _mcp,
    "derle": _derle,
}


if __name__ == "__main__":
    raise SystemExit(main())
