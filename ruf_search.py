"""Flottensuche und Vergleich: Mindestflotte K* des Rufbusses, Mindestfahrzeugzahl N* des Linienbusses, Kosten je Fahrgast, Qualitätsmaße.

Dieselbe Logik fährt live in der App und in den Sweeps (tools/sweep.py), damit die vorgerechnete Messreihe und ein Live-Szenario
dieselben Zahlen für dieselben Einstellungen liefern."""
import math
import time

import ruf_constants as C
from ruf_line import DESIGNS, Line, alloc_vehicles, design_access, design_lines, evaluate, route_table, summarize_line
from ruf_rng import SplitMix64
from ruf_sim import INF, Sim, summarize

NMAX = 30


def lam_of(dens, L):
    """Dichte in Anfragen je Stunde und km² -> Rate je Stunde (Gebiet L x L km)."""
    return dens * L * L


def run_ruf(world, lam, K, cap, W, f, proc="fcfs", B=5.0, search_seed=0, improve=True):
    """Ein Rufbus-Lauf: Anfragenstrom der Rate lam, K Fahrzeuge, Verfahren fcfs (sofortige Einfügung), ols (Einfügen + Verbessern),
    batch (Fenster B min, mit Verbessern) oder batch0 (Fenster B min, nur Einfügen)."""
    sim = Sim(world.tt, world.requests(lam), K, world.starts, cap, W, f)
    if proc == "fcfs":
        sim.run_fcfs()
    elif proc == "ols":
        sim.run_ols(SplitMix64(search_seed))
    elif proc == "batch":
        sim.run_batch(B, SplitMix64(search_seed), improve=improve)
    elif proc == "batch0":
        sim.run_batch(B, SplitMix64(search_seed), improve=False)
    else:
        raise ValueError(proc)
    return sim


def scan_ruf(world, lam, cap, W, f, proc="fcfs", B=5.0, search_seed=0, k_max=80, k_start=None):
    """Flottengröße K von unten hochzählen, bis der Servicegrad dreimal in Folge >= 0,95 ist (Abbruchregel der Messreihe).
    Rückgabe: Liste von Zeilen (K, Kennzahlen aus `summarize`, Rechenzeit), aufsteigend nach K."""
    if k_start is None:
        kg = max(1.0, lam * (world.L / 10.0) / (5.0 if cap == 4 else 8.0))
        k_start = max(1, int(0.3 * kg))
    rows, good, k = [], 0, k_start
    while k <= k_max:
        t = time.perf_counter()
        sim = run_ruf(world, lam, k, cap, W, f, proc=proc, B=B, search_seed=search_seed, improve=(proc != "batch0"))
        s = summarize(sim)
        s.update(K=k, time_s=time.perf_counter() - t, cnt=dict(sim.cnt))
        rows.append(s)
        good = good + 1 if s["served"] >= 0.95 else 0
        if good >= 3:
            break
        k += 1
    return rows


def kstar(rows, target=C.SERVICE_TARGET, theta=None, wait_max=None):
    """Kleinste Flottengröße K, ab der für alle gescannten K' >= K der Servicegrad >= target (und optional mittlere Gesamtzeit <= theta
    bzw. mittlere Wartezeit <= wait_max) gilt. Rückgabe (K, Zeile bei K) oder (inf, None), wenn auch das letzte gescannte K nicht genügt."""
    ok = []
    for r in rows:
        p = r["served"] >= target - 1e-12
        if theta is not None:
            p = p and r["total"] <= theta
        if wait_max is not None:
            p = p and r["wait"] <= wait_max
        ok.append(p)
    if not ok or not ok[-1]:
        return INF, None
    i = len(ok) - 1
    while i > 0 and ok[i - 1]:
        i -= 1
    return rows[i]["K"], rows[i]


def ruf_cost(row, K, basis="fleet"):
    """Fahrzeugstunden je bedientem Fahrgast: Flotte x Messfenster (basis fleet), nur gefahrene Stunden (busy) oder je Anfrage (request)."""
    if basis == "fleet":
        return K * C.MEAS_HOURS / max(row["n_acc"], 1)
    if basis == "request":
        return K * C.MEAS_HOURS / max(row["n_req"], 1)
    return row["busy_h"] / max(row["n_acc"], 1)


def line_phases(seed, design_index, m):
    """Zufallsphase je Linie (Anteil des Taktes), ganzzahlig aus SplitMix64."""
    rng = SplitMix64(int(seed) * 1000 + 99 * 10 + int(design_index))
    return [rng.u32() / 4294967296.0 for _ in range(m)]


def line_summaries(world, design, reqs, seed, nmax=NMAX):
    """Linienbus eines Entwurfs: für jede Fahrzeugzahl N (Linienzahl bis nmax) die Kennzahlen gegen den echten Fahrplan.
    Rückgabe (res {N: Zusammenfassung}, lines, access)."""
    di = DESIGNS.index(design)
    lines = [Line(world, s) for s in design_lines(world, design)]
    access = design_access(world, design)
    m = len(lines)
    u = line_phases(seed, di, m)
    res = {}
    for N in range(m, nmax + 1):
        Nl = alloc_vehicles([ln.C for ln in lines], N)
        LEG, EXP, h = route_table(world, lines, Nl)
        ph = [float(u[l] * h[l]) for l in range(m)]
        res[N] = summarize_line(evaluate(world, lines, Nl, LEG, h, reqs, ph, C.T0_MEAS, C.T1_MEAS, access=access))
    return res, lines, access


def line_pred(kind, val=None, W=None, f=None):
    """Qualitätsmaß für den Linienbus: mittlere Wartezeit (wait), mittlere Gesamtzeit (total), Anteil im Rahmen (env) oder nur Erreichbarkeit."""
    if kind == "wait":
        return lambda v: v["reach"] >= 0.9 and v.get("wait", INF) <= val + 1e-9 and v["rho"] <= 1.0
    if kind == "total":
        return lambda v: v["reach"] >= 0.9 and v.get("total", INF) <= val + 1e-9 and v["rho"] <= 1.0
    if kind == "env":
        key = "env_%g_%g" % (W, f)
        return lambda v: v[key] >= 0.9 and v["rho"] <= 1.0
    if kind == "reach":
        return lambda v: v["reach"] >= 0.9 and v["rho"] <= 1.0
    raise ValueError(kind)


def nstar_line(res, pred):
    """Kleinste Fahrzeugzahl N, ab der pred(res[N]) für alle größeren N gilt; inf, wenn auch N = nmax nicht genügt."""
    Ns = sorted(res)
    ok = [bool(pred(res[N])) for N in Ns]
    if not ok or not ok[-1]:
        return INF
    i = len(ok) - 1
    while i > 0 and ok[i - 1]:
        i -= 1
    return Ns[i]


def line_cost(N, n_req, reach):
    """Fahrzeugstunden je Fahrgast des Linienbusses: N x Messfenster / (Anfragen im Fenster x erreichbarer Anteil)."""
    return N * C.MEAS_HOURS / (n_req * reach)


def crossing(D, cr, cl):
    """Dichte, bei der die Rufbus-Kosten je Fahrgast gleich den Linienbus-Kosten werden (log-lineare Interpolation).
    Rückgabe float; -inf: Linienbus schon an der Untergrenze billiger; +inf: Rufbus im ganzen Bereich billiger."""
    ratio = []
    for r, l in zip(cr, cl):
        ratio.append(0.0 if not math.isfinite(l) else (r / l if l > 0 else INF))
    if ratio[0] >= 1:
        return -INF
    for i in range(len(D) - 1):
        if ratio[i] < 1 <= ratio[i + 1]:
            x0, x1 = math.log(D[i]), math.log(D[i + 1])
            y0, y1 = math.log(max(ratio[i], 1e-9)), math.log(ratio[i + 1])
            return math.exp(x0 + (0 - y0) * (x1 - x0) / (y1 - y0))
    return INF
