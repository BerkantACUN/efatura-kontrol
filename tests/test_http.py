import asyncio
import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from efatura_kontrol import cli, mcp_server

KOK = Path(__file__).resolve().parent.parent

BASLAT = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2025-06-18",
        "capabilities": {},
        "clientInfo": {"name": "test", "version": "0"},
    },
}


def _bos_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _istek(port: int, anahtar: str | None = None, veri: dict | None = None) -> tuple[int, str]:
    basliklar = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }
    if anahtar is not None:
        basliklar["X-API-Key"] = anahtar
    r = urllib.request.Request(
        f"http://127.0.0.1:{port}/mcp",
        data=json.dumps(veri or BASLAT).encode(),
        headers=basliklar,
        method="POST",
    )
    try:
        with urllib.request.urlopen(r, timeout=30) as yanit:
            return yanit.status, yanit.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8")


def _sunucu(port: int, anahtar: str | None) -> subprocess.Popen:
    ortam = {k: v for k, v in os.environ.items() if not k.startswith("EFATURA_")}
    ortam.update({"EFATURA_HOST": "127.0.0.1", "EFATURA_PORT": str(port)})
    if anahtar:
        ortam["EFATURA_API_KEY"] = anahtar
    p = subprocess.Popen(
        [sys.executable, "-m", "efatura_kontrol.cli", "mcp", "--http"],
        env=ortam,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    son = time.monotonic() + 60
    while time.monotonic() < son:
        assert p.poll() is None, "sunucu erken kapandı"
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.5).close()
            return p
        except OSError:
            time.sleep(0.2)
    p.kill()
    pytest.fail("sunucu zamanında açılmadı")


@pytest.fixture
def sunucu():
    acik = []

    def baslat(anahtar: str | None = None) -> int:
        port = _bos_port()
        acik.append(_sunucu(port, anahtar))
        return port

    yield baslat
    for p in acik:
        p.terminate()
        try:
            p.wait(timeout=10)
        except subprocess.TimeoutExpired:
            p.kill()


def test_http_anahtarsiz_acik(sunucu):
    port = sunucu()
    durum, govde = _istek(port)
    assert durum == 200 and '"serverInfo"' in govde and "efatura-kontrol" in govde


def test_http_anahtar_zorunlu(sunucu):
    port = sunucu("gizli-anahtar")
    assert _istek(port)[0] == 401
    durum, govde = _istek(port, "yanlis")
    assert durum == 401 and json.loads(govde)["hata"] == "yetkisiz"
    durum, govde = _istek(port, "gizli-anahtar")
    assert durum == 200 and '"serverInfo"' in govde


def test_anahtar_kapisi_lifespan_gecirir():
    cagrilar = []

    async def uygulama(scope, receive, send):
        cagrilar.append(scope["type"])

    kapi = mcp_server._AnahtarKapisi(uygulama, "k")
    asyncio.run(kapi({"type": "lifespan"}, None, None))
    asyncio.run(kapi({"type": "http", "headers": [(b"x-api-key", b"k")]}, None, None))
    assert cagrilar == ["lifespan", "http"]


def test_http_dosya_parametresi_kapali(sunucu):
    port = sunucu()
    ornek = next((KOK / "ornekler").glob("*.xml"))
    cagri = {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/call",
        "params": {"name": "belge_dogrula", "arguments": {"dosya": str(ornek)}},
    }
    durum, govde = _istek(port, veri=cagri)
    assert durum == 200
    assert "uzak-dosya-kapali" in govde
    assert '"gecerli"' not in govde


def test_boyut_siniri_413():
    cagrilar = []

    async def uygulama(scope, receive, send):
        cagrilar.append(await receive())

    def calistir(basliklar, parcalar):
        giden = []
        kuyruk = [{"type": "http.request", "body": p, "more_body": True} for p in parcalar]

        async def receive():
            return kuyruk.pop(0)

        async def send(mesaj):
            giden.append(mesaj)

        sinir = mcp_server._BoyutSiniri(uygulama, sinir=10)
        asyncio.run(sinir({"type": "http", "headers": basliklar}, receive, send))
        return giden

    giden = calistir([(b"content-length", b"11")], [])
    assert giden[0]["status"] == 413 and cagrilar == []
    giden = calistir([], [b"x" * 11])
    assert giden[0]["status"] == 413
    giden = calistir([(b"content-length", b"5")], [b"x" * 5])
    assert giden == [] and len(cagrilar) == 1


def test_http_varsayilanlari_ve_ortam(monkeypatch):
    monkeypatch.setattr(mcp_server, "_UZAK_MOD", False)
    goruldu = {}

    def sahte_run(uygulama, **kw):
        goruldu.update(kw, uygulama=uygulama)

    import uvicorn

    monkeypatch.setattr(uvicorn, "run", sahte_run)
    for k in ("EFATURA_HOST", "EFATURA_PORT", "EFATURA_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    assert cli.main(["mcp", "--http"]) == 0
    assert (goruldu["host"], goruldu["port"]) == ("0.0.0.0", 8080)
    assert not isinstance(goruldu["uygulama"], mcp_server._AnahtarKapisi)

    monkeypatch.setenv("EFATURA_HOST", "127.0.0.1")
    monkeypatch.setenv("EFATURA_PORT", "9000")
    monkeypatch.setenv("EFATURA_API_KEY", "k")
    assert cli.main(["mcp", "--http"]) == 0
    assert (goruldu["host"], goruldu["port"]) == ("127.0.0.1", 9000)
    assert isinstance(goruldu["uygulama"], mcp_server._AnahtarKapisi)
    assert cli.main(["mcp", "--http", "--host", "::", "--port", "1234"]) == 0
    assert (goruldu["host"], goruldu["port"]) == ("::", 1234)
