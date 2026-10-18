"""Rufbus-Sweeps (Port der Vorab-Messreihe auf den ganzzahligen Generator): je (Zelle, Zufalls-Seed) wird die Flottengröße K von unten hochgezählt,
bis der Servicegrad dreimal in Folge >= 0,95 ist (`ruf_search.scan_ruf`, 1:1-Port der Schleife aus der Vorab-Reihe).

Zufall nur aus `ruf_rng` (SplitMix64): die Welt (Haltepunkte, Nachfrage, Anfragenstrom) aus `ruf_network.World(seed, ...)`, die Suchzufälle
(Umlege-/Austauschreihenfolge bei ols/batch) aus der Ganzzahl `search_seed` wie in `ruf_search.run_ruf`:
    ols, batch0: search_seed = 100 * Zufalls-Seed;   batch: search_seed = 100 * Zufalls-Seed + ss  (ss = 1 in der Wiederholung für die Rauschgrenze).

Aufruf:  python -B tools/sweep_ruf.py [Ausgabeordner] [Prozesse]    (Standard: oepnv-planung/messreihe_rufbus_ap0, 6 Prozesse)
Rohdaten: rufbus.jsonl (Gruppen G1-G7), rufbus_extra.jsonl, rufbus_extra2.jsonl, eine Zeile je Lauf; Hub-Konzentration `hub` als Prozent 0/50/100.
"""
import json
import os
import sys
import time
from multiprocessing import Pool

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from ruf_network import World  # noqa: E402
from ruf_search import lam_of, scan_ruf  # noqa: E402

OUT_DIR = os.environ.get("RUF_RAW_DIR") or os.path.join(os.path.dirname(HERE), "..", "oepnv-planung", "messreihe_rufbus_ap0")
DENS = [0.03, 0.06, 0.10, 0.15, 0.20, 0.30, 0.40, 0.60, 0.80, 1.00]
SEEDS = list(range(1, 31))
BASE = dict(L=10.0, hub=50, W=15.0, B=5.0, n=30)
FILES = {"main": "rufbus.jsonl", "extra": "rufbus_extra.jsonl", "extra2": "rufbus_extra2.jsonl"}


def cells_extra():
    out = []
    for dens in DENS:
        out.append(dict(BASE, dens=dens, c=4, f=1.5, proc="ols"))
        out.append(dict(BASE, dens=dens, c=4, f=1.5, proc="fcfs", n=20))
        out.append(dict(BASE, dens=dens, c=4, f=1.5, proc="fcfs", n=40))
    for dens in (0.2, 0.6, 1.0):
        out.append(dict(BASE, dens=dens, c=2, f=1.5, proc="fcfs"))
        out.append(dict(BASE, dens=dens, c=3, f=1.5, proc="fcfs"))
    for dens in (0.2, 0.4, 0.8):
        out.append(dict(BASE, dens=dens, c=4, f=1.5, proc="ols", W=25.0))
    return out


def cells_extra2():
    out = []
    for dens in DENS:
        for c in (1, 2):
            if c == 2 and dens in (0.2, 0.6, 1.0):
                continue      # steht schon in rufbus_extra.jsonl
            out.append(dict(BASE, dens=dens, c=c, f=1.5, proc="fcfs"))
    return out


def cells():
    out = []
    # G1: Hauptraster
    for dens in DENS:
        for c in (4, 8):
            for f in (1.5, 2.0):
                out.append(dict(BASE, dens=dens, c=c, f=f, proc="fcfs"))
            out.append(dict(BASE, dens=dens, c=c, f=1.5, proc="batch"))
        out.append(dict(BASE, dens=dens, c=4, f=2.0, proc="batch"))
        out.append(dict(BASE, dens=dens, c=4, f=1.5, proc="batch0"))
    # G2: Gebietsgröße
    for L in (6.0, 16.0):
        for dens in DENS:
            if L == 16.0 and dens > 0.40:
                continue
            out.append(dict(BASE, L=L, dens=dens, c=4, f=1.5, proc="fcfs"))
    # G3: maximale Wartezeit
    for W in (10.0, 25.0):
        for dens in DENS:
            out.append(dict(BASE, W=W, dens=dens, c=4, f=1.5, proc="fcfs"))
    # G4: Nachfragestruktur (Hub-Konzentration 0 und 100 Prozent)
    for hub in (0, 100):
        for dens in DENS:
            out.append(dict(BASE, hub=hub, dens=dens, c=4, f=1.5, proc="fcfs"))
    # G6: Batchfenster
    for B in (2.0, 10.0):
        for dens in (0.2, 0.4, 0.8):
            out.append(dict(BASE, B=B, dens=dens, c=4, f=1.5, proc="batch"))
    # G7: Wiederholung der Batch-Suche mit anderem Suchzufall (Rauschgrenze)
    for dens in (0.2, 0.4, 0.8):
        out.append(dict(BASE, dens=dens, c=4, f=1.5, proc="batch", ss=1))
    return out


_worlds = {}


def get_world(seed, L, hub, n):
    k = (seed, L, hub, n)
    if k not in _worlds:
        if len(_worlds) > 6:
            _worlds.clear()
        _worlds[k] = World(seed, L=L, n_stops=n, hub_pct=hub)
    return _worlds[k]


def task(args):
    group, cell, seed = args
    w = get_world(seed, cell["L"], cell["hub"], cell["n"])
    lam = lam_of(cell["dens"], cell["L"])
    proc = cell["proc"]
    ss = cell.get("ss", 0)
    if proc == "batch":
        search_seed = seed * 100 + ss
    elif proc in ("ols", "batch0"):
        search_seed = seed * 100
    else:
        search_seed = 0
    rows = scan_ruf(w, lam, cell["c"], cell["W"], cell["f"], proc=proc, B=cell["B"], search_seed=search_seed)
    out = []
    for s in rows:
        row = dict(cell)
        row.update(seed=seed, lam=lam, **s)
        out.append(row)
    return group, out


def main(out_dir=OUT_DIR, procs=6):
    os.makedirs(out_dir, exist_ok=True)
    jobs = []
    for group, fn in (("main", cells), ("extra", cells_extra), ("extra2", cells_extra2)):
        cs = fn()
        print(group, "Zellen", len(cs), flush=True)
        jobs += [(group, c, s) for c in cs for s in SEEDS]
    jobs.sort(key=lambda j: -j[1]["dens"] * j[1]["L"] ** 2)   # teure zuerst
    print("Aufträge", len(jobs), flush=True)
    t0 = time.time()
    done = 0
    fhs = {g: open(os.path.join(out_dir, fn), "w", encoding="utf-8") for g, fn in FILES.items()}
    try:
        with Pool(procs) as pool:
            for group, rows in pool.imap_unordered(task, jobs, chunksize=1):
                for r in rows:
                    fhs[group].write(json.dumps(r, ensure_ascii=False) + "\n")
                fhs[group].flush()
                done += 1
                if done % 200 == 0:
                    print(done, "/", len(jobs), "%.0fs" % (time.time() - t0), flush=True)
    finally:
        for fh in fhs.values():
            fh.close()
    print("fertig %.0fs" % (time.time() - t0), flush=True)
    with open(os.path.join(out_dir, "sweep_ruf_wallclock.txt"), "w", encoding="utf-8") as fh:
        fh.write("%.1f\n" % (time.time() - t0))


if __name__ == "__main__":
    od = sys.argv[1] if len(sys.argv) > 1 else OUT_DIR
    npr = int(sys.argv[2]) if len(sys.argv) > 2 else 6
    main(od, npr)
