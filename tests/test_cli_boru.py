import subprocess
import sys

import pytest


@pytest.mark.skipif(sys.platform == "win32", reason="Windows'ta kapanan boru EINVAL ile bildirilir")
def test_okuyan_kapaninca_traceback_yok(ornekler, tmp_path):
    veri = (ornekler / "temel_fatura.xml").read_bytes()
    for i in range(150):  # --json çıktısı boru tamponunu (64 KB) aşsın
        (tmp_path / f"f{i:03d}.xml").write_bytes(veri)
    p = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "efatura_kontrol.cli",
            "toplu",
            str(tmp_path),
            "--json",
            "--isci",
            "1",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert p.stdout.read(100).startswith(b"{")
    p.stdout.close()
    hata = p.stderr.read().decode("utf-8", "replace")
    assert p.wait(timeout=120) == 141
    assert "Traceback" not in hata and "BrokenPipeError" not in hata
