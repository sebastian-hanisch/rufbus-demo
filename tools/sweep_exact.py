"""Kleine Instanzen (Port der Vorab-Messreihe): FCFS, Batch und Offline-Heuristik gegen den exakten Referenzwert (lexikografisch: bediente
Anfragen, dann Fahr+Haltezeit). n Anfragen in einem Fenster von `span` Minuten (span 0 = "Los": alle gleichzeitig bekannt), K Fahrzeuge,
Gebiet 10 x 10 km mit 30 Haltepunkten.

Zufall nur aus SplitMix64 (kein random-Modul). Eigene Stream-Nummern (Ströme `seed + (Nummer << 40)`; die Nummern 1-4 gehören `ruf_network`):
    11: Beginn des Fensters   t_lo = 60 + 100 * u32 / 2^32 min
    12: Auswahl der n Anfragen aus dem Fenster (Fisher-Yates-Mischen der Kandidaten, die ersten n, nach Zeit sortiert)
    13: Suchzufall von Batch (Umlege-/Austauschreihenfolge)
Die Welt ist `World(1 + seed % 30)`, die Anfragen sind Teilmenge des Basis-Stroms mit 120/h.

Aufruf:  python -B tools/sweep_exact.py [Ausgabeordner] [Prozesse]    Rohdaten: exact.jsonl"""
import json
import os
import sys
import time
from multiprocessing import Pool

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from ruf_constants import DWELL, SLACK  # noqa: E402
from ruf_exact import exact_solve2, exact_solve_flex, offline_heuristic  # noqa: E402
from ruf_network import World  # noqa: E402
from ruf_rng import SplitMix64  # noqa: E402
from ruf_sim import INF, Sim  # noqa: E402

OUT_DIR = os.environ.get("RUF_RAW_DIR") or os.path.join(os.path.dirname(HERE), "..", "oepnv-planung", "messreihe_rufbus_ap0")
NODE_LIMIT = 3_000_000
STREAM_START, STREAM_PICK, STREAM_BATCH = 11, 12, 13


def stream(seed, nr):
    return SplitMix64(int(seed) + (nr << 40))


def make(seed, n, span):
    w = World(1 + seed % 30, L=10.0)
    allr = w.requests(120.0)
    t_lo = 60.0 + 100.0 * stream(seed, STREAM_START).u32() / 4294967296.0
    pool = [r for r in allr if t_lo <= r[0] < t_lo + span]
    stream(seed, STREAM_PICK).shuffle(pool)
    pool = sorted(pool[:n])
    reqs = [(r[0] - t_lo, r[1], r[2]) for r in pool]
    return w, reqs


def task(args):
    seed, n, K, span, cap, W, f = args
    w, reqs = make(seed, n, max(span, 40.0))
    if span == 0.0:      # Los: alle Anfragen gleichzeitig bekannt (Anfragezeit 0)
        reqs = [(0.0, o, d) for _, o, d in reqs]
    n = len(reqs)
    starts = w.starts[:K]
    rel = [r[0] for r in reqs]
    ddl = [t + W for t in rel]
    rmax = [f * (w.tt[o][d] + DWELL) + SLACK for _, o, d in reqs]
    ro = [r[1] for r in reqs]
    rd = [r[2] for r in reqs]
    row = dict(seed=seed, n=n, K=K, span=span, cap=cap, W=W, f=f)
    t = time.time()
    served, cost, comp, nodes = exact_solve_flex(starts, rel, ddl, rmax, ro, rd, w.tt, DWELL, cap, node_limit=NODE_LIMIT)
    row["ex_served"], row["ex_cost"], row["ex_complete"], row["ex_time"], row["ex_nodes"] = served, cost, comp, time.time() - t, nodes
    t = time.time()
    es, ec, _ = exact_solve2(starts, rel, ddl, rmax, ro, rd, w.tt, DWELL, cap, node_limit=NODE_LIMIT)
    row["early_served"], row["early_cost"], row["early_time"] = es, ec, time.time() - t
    for name in ("fcfs", "batch"):
        sim = Sim(w.tt, reqs, K, starts, cap, W, f)
        t = time.time()
        if name == "fcfs":
            sim.run_fcfs()
        elif span == 0.0:
            sim.advance(0.0)
            sim.plan_batch(list(range(len(reqs))), 0.0, stream(seed, STREAM_BATCH))
            sim.advance(INF)
        else:
            sim.run_batch(5.0, stream(seed, STREAM_BATCH))
        row[name + "_time"] = time.time() - t
        row[name + "_served"] = sum(1 for x in sim.status if x == 1)
        row[name + "_cost"] = sum(b - a for a, b in sim.busy)
    t = time.time()
    s, c = offline_heuristic(starts, rel, ddl, rmax, ro, rd, w.tt, DWELL, cap)
    row["off_served"], row["off_cost"], row["off_time"] = s, c, time.time() - t
    return row


def make_jobs():
    jobs = []
    for seed in range(1, 61):
        for K in (1, 2, 3):
            jobs.append((seed, 8, K, 40.0, 4, 15.0, 1.5))
    # kleinere Last (wenig Konkurrenz) und höhere Last
    for seed in range(1, 61):
        jobs.append((100 + seed, 6, 2, 40.0, 4, 15.0, 1.5))
        jobs.append((200 + seed, 8, 2, 25.0, 4, 15.0, 1.5))
    for seed in range(1, 101):
        for K in (1, 2, 3):
            for W in (15.0, 30.0):
                jobs.append((300 + seed, 8, K, 0.0, 4, W, 1.5))
        if seed <= 30:
            jobs.append((500 + seed, 10, 3, 0.0, 4, 30.0, 1.5))
    return jobs


def main(out_dir=OUT_DIR, procs=6):
    os.makedirs(out_dir, exist_ok=True)
    jobs = make_jobs()
    jobs.sort(key=lambda j: -(j[1] * 10 + j[2]) * (3 if j[5] == 30.0 else 1))   # teure zuerst
    t0 = time.time()
    with Pool(procs) as pool, open(os.path.join(out_dir, "exact.jsonl"), "w", encoding="utf-8") as fh:
        for i, r in enumerate(pool.imap_unordered(task, jobs, chunksize=1)):
            fh.write(json.dumps(r) + "\n")
            fh.flush()
            if (i + 1) % 100 == 0:
                print(i + 1, "/", len(jobs), "%.0fs" % (time.time() - t0), flush=True)
    print("fertig %.0fs" % (time.time() - t0), flush=True)
    with open(os.path.join(out_dir, "sweep_exact_wallclock.txt"), "w", encoding="utf-8") as fh:
        fh.write("%.1f\n" % (time.time() - t0))


if __name__ == "__main__":
    od = sys.argv[1] if len(sys.argv) > 1 else OUT_DIR
    npr = int(sys.argv[2]) if len(sys.argv) > 2 else 6
    main(od, npr)
