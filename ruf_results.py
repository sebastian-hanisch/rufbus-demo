"""Vorgerechnete Messreihe (data/ruf_results.json, erzeugt von tools/sweep_*.py, tools/analyse.py, tools/dump_results.py): Laden und Abfragen.

Nichts hier rechnet im Browser; alle Zahlen stammen aus 30 Zufalls-Seeds je Zelle (siehe `meta`)."""
import json
import math
import os
import pathlib
from functools import lru_cache

PATH = pathlib.Path(os.environ.get("RUF_RESULTS_PATH") or pathlib.Path(__file__).parent / "data" / "ruf_results.json")
INF = float("inf")


def _decode(o):
    """±Unendlich steht in der Datei als "inf" / "-inf" (JSON kennt kein Infinity); hier wieder als Zahl."""
    if isinstance(o, dict):
        return {k: _decode(v) for k, v in o.items()}
    if isinstance(o, list):
        return [_decode(v) for v in o]
    if o == "inf":
        return INF
    if o == "-inf":
        return -INF
    return o


@lru_cache(maxsize=1)
def load():
    with open(PATH, encoding="utf-8") as fh:
        return _decode(json.load(fh))


def meta():
    return load().get("meta", {})


def base_rows():
    """Rufbus-Basiszelle (FCFS, 4 Plätze, Umweg 1,5, Wartezeit 15 min, 10 x 10 km, 30 Haltepunkte): eine Zeile je Dichte."""
    return load()["ruf_base"]


def densities():
    return [r["dens"] for r in base_rows()]


def variants():
    """Alle Kipppunkt-Zellen (Qualitätsmaß und Variante)."""
    return load()["cross"]


def variant_by_label(part):
    for c in variants():
        if part in c["label"]:
            return c
    raise KeyError(part)


def is_none(x):
    """Kein Kipppunkt im untersuchten Bereich: der Rufbus ist überall billiger."""
    return x is None or x == INF


def is_low(x):
    return x == -INF


def fmt_crossing(x, digits=2):
    if is_none(x):
        return "kein Kipppunkt"
    if is_low(x):
        return "Linienbus schon an der Untergrenze billiger"
    return f"{x:.{digits}f}".replace(".", ",")


def lam_text(c):
    """Kipppunkt in Anfragen je Stunde im jeweiligen Gebiet."""
    x = c.get("lam_cross")
    if is_none(x) or is_low(x):
        return fmt_crossing(x)
    return f"{x:.0f}"


def boot_text(c):
    if c.get("boot_p10") is None:
        return "-"
    return f"{c['boot_p10']:.2f} bis {c['boot_p90']:.2f}".replace(".", ",")


MEASURE_KEY = {"wait": "wait", "t30": "total30", "t35": "total35", "t40": "total40", "t45": "total45"}


def band_for(measure, design, dens):
    """P10 / Median / P90 des Kostenverhältnisses Rufbus / Linienbus bei dieser Dichte (Basiszelle, über die Zufalls-Seeds) oder None."""
    tab = load().get("ratio_band")
    try:
        b = tab[MEASURE_KEY[measure]][design]
    except (KeyError, TypeError):
        return None
    ds = b["D"]
    i = min(range(len(ds)), key=lambda k: abs(math.log(ds[k]) - math.log(dens)))
    if abs(math.log(ds[i]) - math.log(dens)) > math.log(1.6):
        return None
    return b["p10"][i], b["med"][i], b["p90"][i]


def ks_by_seed(dens):
    """K* und N* (Entwürfe R, S2, P1; Maß gleiche Wartezeit) je Zufalls-Seed der Basiszelle bei dieser Dichte, oder None."""
    tab = load().get("ruf_ks_by_seed")
    if not tab:
        return None
    return tab.get(str(dens)) or tab.get(f"{dens:g}")
