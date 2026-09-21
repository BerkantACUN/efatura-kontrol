from pathlib import Path

import pytest

ORNEKLER = Path(__file__).resolve().parent.parent / "ornekler"


@pytest.fixture(scope="session")
def ornekler() -> Path:
    return ORNEKLER


@pytest.fixture(scope="session")
def temel_fatura() -> bytes:
    return (ORNEKLER / "temel_fatura.xml").read_bytes()


@pytest.fixture(scope="session")
def tevkifat_fatura() -> bytes:
    return (ORNEKLER / "tevkifat_fatura.xml").read_bytes()


@pytest.fixture(scope="session")
def earsiv_fatura() -> bytes:
    return (ORNEKLER / "earsiv_fatura.xml").read_bytes()


@pytest.fixture(scope="session")
def irsaliye() -> bytes:
    return (ORNEKLER / "irsaliye.xml").read_bytes()


def degistir(veri: bytes, eski: str, yeni: str, sayi: int = 1) -> bytes:
    veri = veri.replace(b"\r\n", b"\n")
    e, y = eski.encode("utf-8"), yeni.encode("utf-8")
    assert e in veri, eski
    return veri.replace(e, y, sayi)
