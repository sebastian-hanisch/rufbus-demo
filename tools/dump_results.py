"""Schreibt aus auswertung.json (tools/analyse.py) die kompakte Ergebnisdatei data/ruf_results.json für die App.

Aufruf:  python -B tools/dump_results.py [Pfad zu auswertung.json] [Ausgabedatei]
Standard: oepnv-planung/messreihe_rufbus_ap0/auswertung.json -> rufbus-demo/data/ruf_results.json

Regeln: UTF-8, +inf wird als String "inf", -inf als "-inf" geschrieben (NaN als null): bei crossing/lam_cross/boot_* heißt "inf" kein Kipppunkt
(Rufbus überall billiger), "-inf" Linienbus schon an der Untergrenze billiger; in Kosten-/N*-Listen heißt "inf" Linienbus (oder Rufbus) nicht erreichbar.
Alle Gleitkommazahlen auf 6 gültige Stellen gerundet, keine Rohdaten, kompakte Trennzeichen. `curves`: Linienbus-Kurven nur bei den in der
Vorab-Reihe genannten Fahrzeugzahlen (2, 4, 6, 8, 10, 12, 14, 16, 20, 24, 30); die Rufbus-Kurven bleiben vollständig. Sonst wird nichts weggelassen."""
import json
import math
import os
import sys

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.environ.get("RUF_RAW_DIR") or os.path.join(os.path.dirname(HERE), "..", "oepnv-planung", "messreihe_rufbus_ap0")
SRC = os.path.join(RAW, "auswertung.json")
DST = os.path.join(os.path.dirname(HERE), "data", "ruf_results.json")
KEEP_N = {"2", "4", "6", "8", "10", "12", "14", "16", "20", "24", "30"}


def rnd(o):
    if isinstance(o, dict):
        return {k: rnd(v) for k, v in o.items()}
    if isinstance(o, list):
        return [rnd(v) for v in o]
    if isinstance(o, bool):
        return o
    if isinstance(o, float):
        if math.isnan(o):
            return None
        if math.isinf(o):
            return "inf" if o > 0 else "-inf"
        return float("%.6g" % o)
    return o


def main(src=SRC, dst=DST):
    with open(src, encoding="utf-8") as fh:
        R = json.load(fh)
    for k, v in list(R["curves"].items()):
        if k.startswith("line_"):
            R["curves"][k] = {n: x for n, x in v.items() if n in KEEP_N}
    out = rnd(R)
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    with open(dst, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, separators=(",", ":"))
    print("geschrieben:", dst, "%.0f kB" % (os.path.getsize(dst) / 1024.0))


if __name__ == "__main__":
    main(*(sys.argv[1:3]))
