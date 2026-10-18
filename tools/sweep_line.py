"""Linienbus-Sweeps (Port der Vorab-Messreihe): je (Gebiet, Hub-Konzentration, Haltepunktzahl, Zufalls-Seed, Dichte, Entwurf) alle Fahrzeugzahlen N
durchrechnen (`ruf_search.line_summaries`, 1:1-Port der Schleife aus der Vorab-Reihe). Die Zufallsphase des Fahrplans je Linie kommt aus
`ruf_search.line_phases` (SplitMix64), die Welt aus `ruf_network.World`; kein numpy-Zufall.

Aufruf:  python -B tools/sweep_line.py [Ausgabeordner] [Prozesse]    (Standard: oepnv-planung/messreihe_rufbus_ap0, 6 Prozesse)
Rohdaten: linie.jsonl (eine Zeile je Zelle x Entwurf; `res` = {N: Zusammenfassung}; `hub` in Prozent)."""
import json
import os
import sys
import time
from multiprocessing import Pool

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

from ruf_line import DESIGNS  # noqa: E402
from ruf_network import World  # noqa: E402
from ruf_search import NMAX, lam_of, line_summaries  # noqa: E402
from sweep_ruf import DENS, OUT_DIR, SEEDS  # noqa: E402

COMBOS = [(10.0, 50, 30), (6.0, 50, 30), (16.0, 50, 30), (10.0, 0, 30), (10.0, 100, 30), (10.0, 50, 20), (10.0, 50, 40)]


def task(args):
    L, hub, n, seed = args
    w = World(seed, L=L, n_stops=n, hub_pct=hub)
    rows = []
    reqs_by_dens = {d: w.requests(lam_of(d, L)) for d in DENS}
    for design in DESIGNS:
        for dens in DENS:
            res, lines, _ = line_summaries(w, design, reqs_by_dens[dens], seed, nmax=NMAX)
            rows.append(dict(L=L, hub=hub, n=n, seed=seed, dens=dens, design=design, cycle=[ln.C for ln in lines],
                             nstops=[ln.P for ln in lines], res={str(N): v for N, v in res.items()}))
    return rows


def main(out_dir=OUT_DIR, procs=6):
    os.makedirs(out_dir, exist_ok=True)
    jobs = [(L, hub, n, s) for (L, hub, n) in COMBOS for s in SEEDS]
    t0 = time.time()
    done = 0
    with Pool(procs) as pool, open(os.path.join(out_dir, "linie.jsonl"), "w", encoding="utf-8") as fh:
        for rows in pool.imap_unordered(task, jobs, chunksize=1):
            for r in rows:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")
            fh.flush()
            done += 1
            if done % 15 == 0:
                print(done, "/", len(jobs), "%.0fs" % (time.time() - t0), flush=True)
    print("fertig %.0fs" % (time.time() - t0), flush=True)
    with open(os.path.join(out_dir, "sweep_line_wallclock.txt"), "w", encoding="utf-8") as fh:
        fh.write("%.1f\n" % (time.time() - t0))


if __name__ == "__main__":
    od = sys.argv[1] if len(sys.argv) > 1 else OUT_DIR
    npr = int(sys.argv[2]) if len(sys.argv) > 2 else 6
    main(od, npr)
