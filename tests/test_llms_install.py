import asyncio
import json
import re
from pathlib import Path

from efatura_kontrol import mcp_server


def test_llms_install_araclarla_uyumlu():
    metin = Path("llms-install.md").read_text(encoding="utf-8")
    bloklar = [json.loads(b) for b in re.findall(r"```json\n(.*?)```", metin, re.S)]
    yerel = bloklar[0]["mcpServers"]["efatura-kontrol"]
    assert yerel["args"] == ["efatura-kontrol", "mcp"]
    araclar = {a.name for a in asyncio.run(mcp_server.mcp.list_tools())}
    assert set(yerel["autoApprove"]) == araclar
    assert bloklar[1]["mcpServers"]["efatura-kontrol"]["url"].endswith("/mcp")
