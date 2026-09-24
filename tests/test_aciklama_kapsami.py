import importlib.util
from pathlib import Path

ARAC = Path(__file__).resolve().parent.parent / "araclar" / "sematron_kapsam.py"


def _arac():
    spec = importlib.util.spec_from_file_location("sematron_kapsam", ARAC)
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)
    return modul


def test_tetiklenen_her_kuralin_aciklamasi_var():
    from efatura_kontrol.kod import _aciklamalar

    arac = _arac()
    tum = arac.kurallar()
    aciklamali = {k for k in _aciklamalar() if k in tum}
    assert len(aciklamali) / len(tum) >= 0.77
    sayac, toplam = arac.siklik()
    assert toplam > 900
    eksik = sorted(k for k in sayac if k.startswith("sch-") and k not in aciklamali)
    assert eksik == [], eksik
