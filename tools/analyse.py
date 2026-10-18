"""Auswertung der neuen Rohdaten (Port von oepnv-planung/messreihe_rufbus/auswerten.py auf den ganzzahligen Generator) -> auswertung.json + auswertung.txt.

Aufruf:  python -B tools/analyse.py [Datenordner]     (Standard: oepnv-planung/messreihe_rufbus_ap0, dort liegen Rohdaten und Ausgabe)

Zufall: nur im Bootstrap der Kipppunkte (300 Resamples über die Zufalls-Seeds). Er benutzt `numpy.random.default_rng(BOOT_SEED)` mit der festen
Ganzzahl BOOT_SEED = 12345; das ist erlaubt, weil das Ergebnis als JSON eingefroren wird (Auswertung, nicht Simulation). Die Simulationen selbst
(Welt, Anfragen, Suchzufall) verwenden ausschließlich ruf_rng.SplitMix64.

Die Auswertung benutzt dieselben Funktionen wie die App (`ruf_search.kstar`, `nstar_line`, `line_pred`, `crossing`), damit Messreihe und Live-Szenario
dieselbe Rechnung teilen. Rohdaten: `hub` steht in Prozent (0/50/100)."""
import collections
import datetime
import json
import math
import os
import platform
import sys

sys.dont_write_bytecode = True
HERE_TOOLS = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE_TOOLS))

import numpy as np  # noqa: E402

import ruf_constants as C  # noqa: E402
from ruf_search import crossing, kstar, line_pred, nstar_line  # noqa: E402

DEFAULT_RAW = os.environ.get("RUF_RAW_DIR") or os.path.join(os.path.dirname(HERE_TOOLS), "..", "oepnv-planung", "messreihe_rufbus_ap0")
DATA = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_RAW
OUTJ = os.path.join(DATA, "auswertung.json")
OUTT = os.path.join(DATA, "auswertung.txt")
BOOT_SEED = 12345
BOOT_N = 300
T_H = C.MEAS_HOURS
INF = float("inf")
DENS = [0.03, 0.06, 0.10, 0.15, 0.20, 0.30, 0.40, 0.60, 0.80, 1.00]
DESIGNS = ["R", "S1", "S2", "S3", "S4", "P1", "P2"]
BASE = dict(L=10.0, hub=50, W=15.0, B=5.0, n=30)
R = {}
TXT = []


def P(*a):
    s = " ".join(str(x) for x in a)
    TXT.append(s)
    print(s, flush=True)


# ------------------------------------------------------------------------------ Laden
def mean_se(x):
    x = np.asarray([v for v in x if np.isfinite(v)], dtype=float)
    if len(x) == 0:
        return (float("nan"), float("nan"), 0)
    if len(x) == 1:
        return (float(x[0]), 0.0, 1)
    return (float(x.mean()), float(x.std(ddof=1) / math.sqrt(len(x))), len(x))


def q(x, p):
    x = np.asarray([v for v in x if np.isfinite(v)], dtype=float)
    return float(np.quantile(x, p)) if len(x) else float("nan")


def qinf(x, p):
    """Quantil mit unerreichbar (inf) als größtem Wert: liefert inf, wenn der Rang in den unerreichbaren Teil fällt."""
    x = np.sort(np.asarray(x, dtype=float))
    big = np.where(np.isfinite(x), x, 1e12)
    v = float(np.quantile(big, p))
    return INF if v > 1e11 else v


def cell_key(r):
    return (r["L"], r["hub"], r["W"], r["B"], r["n"], r["c"], r["f"], r["proc"], r["dens"], r.get("ss", 0))


def load_ruf():
    cells = collections.defaultdict(lambda: collections.defaultdict(list))
    for fn in ("rufbus.jsonl", "rufbus_extra.jsonl", "rufbus_extra2.jsonl"):
        path = os.path.join(DATA, fn)
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                r = json.loads(line)
                cells[cell_key(r)][r["seed"]].append(r)
    for ck_ in cells:
        for s in cells[ck_]:
            cells[ck_][s].sort(key=lambda r: r["K"])
    return cells


CYCLE = {}


def load_line():
    out = collections.defaultdict(dict)   # (L,hub,n,seed,dens) -> design -> {N: res}
    with open(os.path.join(DATA, "linie.jsonl"), encoding="utf-8") as fh:
        for line in fh:
            r = json.loads(line)
            out[(r["L"], r["hub"], r["n"], r["seed"], r["dens"])][r["design"]] = {int(N): v for N, v in r["res"].items()}
            CYCLE[(r["L"], r["hub"], r["n"], r["seed"], r["design"])] = (r["cycle"], r["nstops"])
    return out


def ck(dens, c=4, f=1.5, proc="fcfs", ss=0, **kw):
    b = dict(BASE)
    b.update(kw)
    return (b["L"], b["hub"], b["W"], b["B"], b["n"], c, f, proc, dens, ss)


def safe(pred):
    """Prädikat, das Zellen ohne Anfragen (Zusammenfassung None) als nicht erfüllt wertet."""
    return lambda v: v is not None and pred(v)


ruf = load_ruf()
line = load_line()
n_runs = sum(len(r) for c in ruf.values() for r in c.values())
P("Rufbus-Zellen:", len(ruf), " Läufe:", n_runs)
seeds_per_cell = collections.Counter(len(c) for c in ruf.values())
P("Zufalls-Seeds je Zelle:", dict(seeds_per_cell))
R["n_cells"] = len(ruf)
R["n_runs"] = n_runs
R["seeds_per_cell"] = dict(seeds_per_cell)

# ------------------------------------------------------------------------------ Randprüfung der Suche
edge = 0
cens = 0
tot = 0
for key, cell in ruf.items():
    for s, rows in cell.items():
        tot += 1
        K, r = kstar(rows)
        if r is None:
            cens += 1
        elif K == rows[0]["K"] and K > 1:
            edge += 1
R["scan_edge_low"] = edge
R["scan_censored"] = cens
R["scan_total"] = tot
P("Suchrand: untere Grenze schon bestanden:", edge, " nie bestanden (zensiert):", cens, " von", tot)


# ------------------------------------------------------------------------------ Hilfsfunktionen
def ruf_cost_by_seed(cell, basis="fleet", **std):
    out = {}
    for s, rows in cell.items():
        K, r = kstar(rows, **std)
        if r is None:
            out[s] = (INF, INF, None)
        elif basis == "fleet":
            out[s] = (K, K * T_H / max(r["n_acc"], 1), r)
        elif basis == "request":
            out[s] = (K, K * T_H / max(r["n_req"], 1), r)
        else:
            out[s] = (K, r["busy_h"] / max(r["n_acc"], 1), r)
    return out


def line_by_design(cell_key_, seeds, pred_for_seed, designs=DESIGNS):
    """für jeden Entwurf: {seed: N*}; pred_for_seed(seed) -> Prädikat"""
    L, hub, W, B, n, *_ = cell_key_
    dens = cell_key_[8]
    out = {}
    for d in designs:
        o = {}
        for s in seeds:
            res = line[(L, hub, n, s, dens)][d]
            o[s] = nstar_line(res, safe(pred_for_seed(s)))
        out[d] = o
    return out


def fmt_cross(x):
    if x == INF:
        return "kein Kipppunkt (Rufbus überall billiger)"
    if x == -INF:
        return "Linienbus schon an der Untergrenze billiger"
    return "%.2f" % x


def best_design_costs(dens_list, rkey_fn, std_ruf, pred_fn, basis="fleet"):
    """Je Dichte: Rufbus-Kosten je Seed, Linienbus-Kosten je Seed und Entwurf."""
    res = {"D": dens_list, "ruf": [], "line": [], "ruf_K": [], "line_N": {}}
    for d in dens_list:
        key = rkey_fn(d)
        cell = ruf[key]
        sd = sorted(cell)
        rc = ruf_cost_by_seed(cell, basis=basis, **std_ruf)
        res["ruf"].append([rc[s][1] for s in sd])
        res["ruf_K"].append([rc[s][0] for s in sd])
        preds = pred_fn(rc)
        ld = line_by_design(key, sd, preds)
        nreq = {s: cell[s][0]["n_req"] for s in sd}
        L_, hub_, W_, B_, n_, *_r = key

        def lc(dd, s):
            N = ld[dd][s]
            if not np.isfinite(N):
                return INF
            return N * T_H / (nreq[s] * line[(L_, hub_, n_, s, d)][dd][N]["reach"])
        res["line"].append({dd: [lc(dd, s) for s in sd] for dd in DESIGNS})
        res["line_N"][d] = {dd: [ld[dd][s] for s in sd] for dd in DESIGNS}
    return res


def cross_kind(x):
    """Im JSON werden +-inf zu null; dieses Feld hält fest, was gemeint war: 'wert', 'kein' (Rufbus überall billiger), 'unter' (Linie schon an der Untergrenze billiger)."""
    return "kein" if x == INF else ("unter" if x == -INF else "wert")


def mean_or_inf(v):
    return float(np.mean(v)) if np.all(np.isfinite(v)) else INF


def summarize_cross(res, label, boot=BOOT_N):
    D = res["D"]
    nd = len(D)
    best = None
    for dd in DESIGNS:
        tot_ = np.mean([np.mean(res["line"][i][dd]) if np.all(np.isfinite(res["line"][i][dd])) else 1e9 for i in range(nd)])
        if best is None or tot_ < best[0]:
            best = (tot_, dd)
    dd = best[1]
    mr = [float(np.mean(res["ruf"][i])) for i in range(nd)]
    ml_fixed = [mean_or_inf(res["line"][i][dd]) for i in range(nd)]
    ml_perd = []
    chosen = []
    for i in range(nd):
        cand = {d2: mean_or_inf(res["line"][i][d2]) for d2 in DESIGNS}
        b = min(cand, key=lambda k: cand[k])
        ml_perd.append(cand[b])
        chosen.append(b)
    ml_orac = []
    for i in range(nd):
        arr = np.array([res["line"][i][d2] for d2 in DESIGNS])   # (Entwürfe, Seeds)
        ml_orac.append(float(np.mean(arr.min(axis=0))) if np.all(np.isfinite(arr.min(axis=0))) else INF)
    cx_cell = crossing(D, mr, ml_perd)
    cx = crossing(D, mr, ml_orac)       # Hauptwert: je Instanz (Zufalls-Seed) bester der Linienentwürfe
    by_design = {}
    line_mean_by_design = {}
    line_unreach_by_design = {}
    for d2 in DESIGNS:
        mld = [mean_or_inf(res["line"][i][d2]) for i in range(nd)]
        by_design[d2] = crossing(D, mr, mld)
        line_mean_by_design[d2] = mld
        line_unreach_by_design[d2] = [int(np.sum(~np.isfinite(res["line"][i][d2]))) for i in range(nd)]
    ruf_inf = [int(np.sum(~np.isfinite(res["ruf"][i]))) for i in range(nd)]
    out = dict(crossing_by_design=by_design, ruf_inf=ruf_inf, crossing_cell=cx_cell, label=label, design_fixed=dd, design_per_dens=chosen, ruf_mean=mr,
               line_mean=ml_perd, line_mean_fixed=ml_fixed, line_mean_oracle=ml_orac, crossing=cx, crossing_fixed=crossing(D, mr, ml_fixed),
               crossing_oracle=crossing(D, mr, ml_orac),
               line_mean_by_design=line_mean_by_design, line_unreach_by_design=line_unreach_by_design,
               ruf_cost_p10=[q(res["ruf"][i], 0.1) for i in range(nd)], ruf_cost_p90=[q(res["ruf"][i], 0.9) for i in range(nd)])
    out["crossing_kind"] = cross_kind(cx)
    out["crossing_cell_kind"] = cross_kind(cx_cell)
    out["crossing_by_design_kind"] = {k_: cross_kind(v) for k_, v in by_design.items()}
    rng = np.random.default_rng(BOOT_SEED)
    ns = len(res["ruf"][0])
    bs = []
    for _ in range(boot):
        idx = rng.integers(0, ns, ns)
        mr_b = [float(np.mean(np.asarray(res["ruf"][i])[idx])) for i in range(nd)]
        ml_b = []
        for i in range(nd):
            arr = np.array([np.asarray(res["line"][i][d2])[idx] for d2 in DESIGNS])
            mn = arr.min(axis=0)
            ml_b.append(float(mn.mean()) if np.all(np.isfinite(mn)) else INF)
        bs.append(crossing(D, mr_b, ml_b))
    bs = np.array(bs)
    fin = bs[np.isfinite(bs)]
    out["boot_n"] = boot
    out["boot_seed"] = BOOT_SEED
    out["boot_share_none"] = float(np.mean(bs == INF))
    out["boot_share_lowedge"] = float(np.mean(bs == -INF))
    out["boot_p10"] = float(np.quantile(fin, 0.1)) if len(fin) else None
    out["boot_p90"] = float(np.quantile(fin, 0.9)) if len(fin) else None
    return out


def wait_matched_pred(rc):
    """Prädikat je Seed: mittlere Wartezeit der Linie <= mittlere Wartezeit des Rufbusses bei K* desselben Seeds."""
    def f(s):
        r = rc[s][2]
        w = r["wait"] if r is not None else 0.0
        return line_pred("wait", w)
    return f


def abs_pred(kind, val=None, W=None, f=None):
    def fn(rc):
        return lambda s: line_pred(kind, val, W, f)
    return fn


# ------------------------------------------------------------------------------ 1. Rufbus-Basis
P("\n=== 1. Rufbus, Basis (FCFS, c=4, f=1,5, W=15, Gebiet 10x10, 30 Haltepunkte, Nachfrage-Hub 50 %): Mindestflotte K* für Servicegrad >= 90 %")
hdr = "%5s %6s %6s | %-16s %5s %5s %5s | %5s %5s %5s %5s | %5s %5s %5s %5s %5s | %6s %6s"
P(hdr % ("dens", "lam/h", "n_req", "K* Mittel±SE", "med", "P10", "P90", "wait", "ride", "total", "detour", "serv", "util", "shared", "corid", "occ", "vh/Pax", "busy/Pax"))
base_tab = []
for d in DENS:
    cell = ruf[ck(d)]
    rc = ruf_cost_by_seed(cell)
    ks = [rc[s][0] for s in sorted(cell)]
    rows = [rc[s][2] for s in sorted(cell)]
    m, se, nn = mean_se(ks)
    cost = [rc[s][1] for s in sorted(cell)]
    util = [r["busy_h"] / (rc[s][0] * T_H) for s, r in zip(sorted(cell), rows)]
    busy_pax = [r["busy_h"] / r["n_acc"] for r in rows]
    rec = dict(dens=d, lam=d * 100, n_req=float(np.mean([r["n_req"] for r in rows])), K_mean=m, K_se=se, K_med=q(ks, .5), K_p10=q(ks, .1), K_p90=q(ks, .9),
               wait=float(np.mean([r["wait"] for r in rows])), ride=float(np.mean([r["ride"] for r in rows])), total=float(np.mean([r["total"] for r in rows])),
               detour=float(np.mean([r["detour"] for r in rows])), served=float(np.mean([r["served"] for r in rows])), util=float(np.mean(util)),
               shared=float(np.mean([r["shared"] for r in rows])), corider=float(np.mean([r["corider"] for r in rows])), occ=float(np.mean([r["occ"] for r in rows])),
               cost=mean_se(cost), cost_med=q(cost, .5), cost_p10=q(cost, .1), cost_p90=q(cost, .9), busy_cost=float(np.mean(busy_pax)), wait_p90=float(np.mean([r["wait_p90"] for r in rows])))
    base_tab.append(rec)
    P("%5.2f %6.1f %6.0f | %5.2f ± %4.2f %-5s %5.1f %5.1f %5.1f | %5.1f %5.1f %5.1f %5.2f | %5.2f %5.2f %5.2f %5.2f %5.2f | %6.3f %6.3f" % (
        d, d * 100, rec["n_req"], m, se, "", rec["K_med"], rec["K_p10"], rec["K_p90"], rec["wait"], rec["ride"], rec["total"], rec["detour"], rec["served"],
        rec["util"], rec["shared"], rec["corider"], rec["occ"], rec["cost"][0], rec["busy_cost"]))
R["ruf_base"] = base_tab
# Potenzgesetz K* ~ lam^a
a_pow = float(np.polyfit(np.log([d * 100 for d in DENS]), np.log([r["K_mean"] for r in base_tab]), 1)[0])
R["power_law_exponent"] = a_pow
P("  Potenzgesetz K* ~ lam^%.3f" % a_pow)

# ------------------------------------------------------------------------------ 2. Linienbus
P("\n=== 2. Linienbus: Mindestzahl Fahrzeuge N* je Entwurf bei GLEICHER mittlerer Wartezeit wie der Rufbus (Basis, FCFS) -- Mittel über Seeds, inf = nie erreicht (N<=30)")
P("%5s | %s" % ("dens", " ".join("%-18s" % d for d in DESIGNS)))
lin_tab = {}
rc_by_dens = {d: ruf_cost_by_seed(ruf[ck(d)]) for d in DENS}
ruf_ks = {}
for d in DENS:
    key = ck(d)
    sd = sorted(ruf[key])
    ld = line_by_design(key, sd, wait_matched_pred(rc_by_dens[d]))
    row = {}
    cells_txt = []
    for dd in DESIGNS:
        v = [ld[dd][s] for s in sd]
        nfin = [x for x in v if np.isfinite(x)]
        row[dd] = dict(mean=float(np.mean(nfin)) if nfin else None, n_inf=len(v) - len(nfin), med=q(v, .5))
        cells_txt.append("%-18s" % (("%.1f (%d unerreicht)" % (np.mean(nfin), len(v) - len(nfin))) if nfin else "alle unerreicht"))
    lin_tab[d] = row
    P("%5.2f | %s" % (d, " ".join(cells_txt)))
    ruf_ks[d] = dict(seeds=sd, K=[rc_by_dens[d][s][0] for s in sd], N_R=[ld["R"][s] for s in sd], N_S2=[ld["S2"][s] for s in sd], N_P1=[ld["P1"][s] for s in sd])
R["line_design_waitmatched"] = lin_tab
R["ruf_ks_by_seed"] = ruf_ks

P("\n    Linienbus (Entwurf R) bei N* (wartegleich): Qualität")
line_q = []
for d in DENS:
    key = ck(d)
    sd = sorted(ruf[key])
    vals = collections.defaultdict(list)
    for s in sd:
        r = rc_by_dens[d][s][2]
        res = line[(10.0, 50, 30, s, d)]["R"]
        N = nstar_line(res, safe(line_pred("wait", r["wait"])))
        if np.isfinite(N):
            v = res[N]
            for k_ in ("wait", "ride", "total", "transfer_share", "rho"):
                vals[k_].append(v.get(k_, 0.0))
            vals["N"].append(N)
            vals["takt"].append(CYCLE[(10.0, 50, 30, s, "R")][0][0] / N)
            vals["cycle"].append(CYCLE[(10.0, 50, 30, s, "R")][0][0])
            vals["env_15_1.5"].append(v["env_15_1.5"])
            vals["env_25_2"].append(v["env_25_2"])
    rec = {k_: float(np.mean(v)) for k_, v in vals.items()}
    rec["dens"] = d
    line_q.append(rec)
    P("    d=%.2f N*=%.1f (Takt %.1f min bei Umlaufzeit %.0f min) wait %.1f ride %.1f total %.1f  | Rufbus total %.1f  ride %.1f | Linie im Versprechen (15,1.5): %.2f (25,2): %.2f  Lastfaktor %.3f" % (
        d, rec["N"], rec["takt"], rec["cycle"], rec["wait"], rec["ride"], rec["total"], base_tab[DENS.index(d)]["total"], base_tab[DENS.index(d)]["ride"], rec["env_15_1.5"], rec["env_25_2"], rec["rho"]))
R["line_quality_R"] = line_q

P("\n    Linienbus nach Fahrzeugzahl N (Dichte 0,40; Mittel über 30 Seeds): Takt, Wartezeit, Fahrzeit, Gesamtzeit, Anteil im Rahmen (25 min, 2,0), Lastfaktor")
line_by_N = {}
for dd in ("R", "S2"):
    tabN = []
    for N in (4, 6, 8, 10, 12, 16, 20, 24, 30):
        vals = collections.defaultdict(list)
        for s_ in range(1, 31):
            res = line[(10.0, 50, 30, s_, 0.4)][dd]
            if N not in res:
                continue
            v = res[N]
            vals["wait"].append(v["wait"])
            vals["ride"].append(v["ride"])
            vals["total"].append(v["total"])
            vals["env"].append(v["env_25_2"])
            vals["env_strict"].append(v["env_15_1.5"])
            vals["rho"].append(v["rho"])
            vals["takt"].append(CYCLE[(10.0, 50, 30, s_, dd)][0][0] / N)
            vals["transf"].append(v["transfer_share"])
        rec = {k_: float(np.mean(v)) for k_, v in vals.items()}
        rec["N"] = N
        tabN.append(rec)
        P("    %s N=%2d: Takt (Umlaufzeit/N, erste Linie) %5.1f min  Wartezeit %5.1f  Fahrzeit %5.1f  Gesamt %5.1f  Umsteiger %.2f  im Rahmen (25,2) %.2f  im Rahmen (15,1.5) %.2f  Last %.3f" % (
            dd, N, rec["takt"], rec["wait"], rec["ride"], rec["total"], rec["transf"], rec["env"], rec["env_strict"], rec["rho"]))
    line_by_N[dd] = tabN
R["line_by_N"] = line_by_N

# ------------------------------------------------------------------------------ 3. Kipppunkte
P("\n=== 3. Kipppunkte (Dichte in Anfragen je Stunde und km^2, bei der Rufbus-Kosten je Fahrgast = Linienbus-Kosten)")
cross_tab = []
cross_res = {}


def run_cross(label, rkey_fn, std_ruf, pred_fn, dens_list=DENS, basis="fleet", L=10.0, tag=None):
    res = best_design_costs(dens_list, rkey_fn, std_ruf, pred_fn, basis=basis)
    sm = summarize_cross(res, label)
    sm["L"] = L
    sm["lam_cross"] = (sm["crossing"] * L * L) if np.isfinite(sm["crossing"]) else sm["crossing"]
    cross_tab.append(sm)
    cross_res[tag or label] = res
    infs = sum(sm["ruf_inf"])
    P("%-62s Kipppunkt (bester Entwurf je Instanz) %s Anfr./h/km2 = %s Anfr./h (Bootstrap P10-P90: %s; ohne Kipppunkt %.0f %%) | bester Entwurf je Dichte-Zelle: %s, fester Entwurf %s: %s%s" % (
        label, fmt_cross(sm["crossing"]), fmt_cross(sm["lam_cross"]),
        ("%.2f-%.2f" % (sm["boot_p10"], sm["boot_p90"])) if sm["boot_p10"] is not None else "-", 100 * sm["boot_share_none"], fmt_cross(sm["crossing_cell"]), sm["design_fixed"],
        fmt_cross(sm["crossing_fixed"]),
        ("  [Rufbus in %d Seed-Dichte-Paaren im Scanbereich nicht erreichbar]" % infs) if infs else ""))
    P("%-62s   Kipppunkt je festem Linienentwurf: %s" % ("", "  ".join("%s %s" % (k_, fmt_cross(v)) for k_, v in sm["crossing_by_design"].items())))
    return res, sm


for proc, c, f in [("fcfs", 4, 1.5), ("fcfs", 8, 1.5), ("fcfs", 4, 2.0), ("fcfs", 8, 2.0), ("batch", 4, 1.5), ("batch", 8, 1.5), ("batch", 4, 2.0), ("ols", 4, 1.5), ("batch0", 4, 1.5)]:
    run_cross("wartegleich | %s c=%d f=%.1f (L=10, W=15)" % (proc, c, f), lambda d, proc=proc, c=c, f=f: ck(d, c=c, f=f, proc=proc), {}, wait_matched_pred,
              tag="wait|%s|%d|%.1f" % (proc, c, f))

for L in (6.0, 16.0):
    dl = [d for d in DENS if not (L == 16.0 and d > 0.4)]
    run_cross("wartegleich | Gebiet %.0fx%.0f km (FCFS c=4 f=1.5)" % (L, L), lambda d, L=L: ck(d, L=L), {}, wait_matched_pred, dl, L=L)
for W in (10.0, 25.0):
    run_cross("wartegleich | W=%g (FCFS c=4 f=1.5)" % W, lambda d, W=W: ck(d, W=W), {}, wait_matched_pred)
for hub in (0, 100):
    run_cross("wartegleich | Nachfrage-Hub %.1f" % (hub / 100.0), lambda d, hub=hub: ck(d, hub=hub), {}, wait_matched_pred)
for nn in (20, 40):
    run_cross("wartegleich | %d Haltepunkte" % nn, lambda d, nn=nn: ck(d, n=nn), {}, wait_matched_pred)

for tg in (0.8, 0.95):
    run_cross("wartegleich | Servicegrad-Ziel Rufbus %.0f %% (FCFS c=4 f=1.5)" % (100 * tg), lambda d: ck(d), dict(target=tg), wait_matched_pred)
run_cross("wartegleich | Rufbus-Kosten nach GEFAHRENEN Stunden (statt Flotte)", lambda d: ck(d), {}, wait_matched_pred, basis="busy")
run_cross("wartegleich | Kosten je ANFRAGE (nicht je Bedientem; Rufbus 7-8 Prozent unbedient)", lambda d: ck(d), {}, wait_matched_pred, basis="request")

for wmax in (5.0, 8.0, 12.0, 20.0):
    run_cross("Wartegrenze mittlere Wartezeit <= %g min (beide)" % wmax, lambda d: ck(d), dict(wait_max=wmax), abs_pred("wait", wmax))
for th in (25.0, 30.0, 35.0, 40.0, 45.0, 60.0):
    run_cross("Gesamtzeit mittlere Reisezeit <= %g min (beide)" % th, lambda d: ck(d), dict(theta=th), abs_pred("total", th), tag="total|%g" % th)

P("\n    Versprechen (Anteil im Zeitrahmen W + f*direkt + 2 min >= 90 %), Linienbus: bei welchem N* (R) erreicht? Zähle unerreichte Seeds")
env_tab = {}
for (W_, f_) in [(10.0, 1.5), (15.0, 1.5), (15.0, 2.0), (25.0, 2.0), (40.0, 2.0)]:
    rowv = []
    for d in DENS:
        sd = sorted(ruf[ck(d)])
        ns = [nstar_line(line[(10.0, 50, 30, s, d)]["R"], safe(line_pred("env", None, W_, f_))) for s in sd]
        fin = [x for x in ns if np.isfinite(x)]
        rowv.append((len(ns) - len(fin), float(np.mean(fin)) if fin else None))
    env_tab["%g_%g" % (W_, f_)] = rowv
    P("    Versprechen (W=%g, f=%.1f): " % (W_, f_) + "  ".join("d=%.2f: %s" % (d, ("N*=%.1f (%d unerr.)" % (v[1], v[0])) if v[1] is not None else "alle unerr.") for d, v in zip(DENS, rowv)))
R["env_line_R"] = env_tab
R["cross"] = cross_tab

# ------------------------------------------------------------------------------ 3e. Verhältnisband (App)
P("\n=== 3e. Verhältnis Rufbus-Kosten / Linienbus-Kosten je Fahrgast: P10 / Median / P90 über die Zufalls-Seeds (Linie unmöglich -> 0)")
ratio_band = {}
for mname, tag in (("wait", "wait|fcfs|4|1.5"), ("total30", "total|30"), ("total35", "total|35"), ("total40", "total|40"), ("total45", "total|45")):
    res = cross_res[tag]
    ratio_band[mname] = {}
    for choice in ("best", "R", "S2", "P1"):
        p10, med, p90 = [], [], []
        for i in range(len(DENS)):
            rr = np.asarray(res["ruf"][i], dtype=float)
            if choice == "best":
                ll = np.min(np.array([res["line"][i][dd] for dd in DESIGNS]), axis=0)
            else:
                ll = np.asarray(res["line"][i][choice], dtype=float)
            with np.errstate(divide="ignore", invalid="ignore"):
                ratio = np.where(np.isfinite(ll), rr / ll, 0.0)
            p10.append(qinf(ratio, 0.1))
            med.append(qinf(ratio, 0.5))
            p90.append(qinf(ratio, 0.9))
        ratio_band[mname][choice] = dict(D=DENS, p10=p10, med=med, p90=p90)
        P("  %-8s %-4s Median je Dichte: %s" % (mname, choice, " ".join("%.2f" % x for x in med)))
R["ratio_band"] = ratio_band

# ------------------------------------------------------------------------------ 4. Verfahren
P("\n=== 4. Verfahrensvergleich beim Rufbus (c=4, f=1.5, W=15): Mindestflotte K* je Seed, gepaart gegen FCFS")
proc_tab = {}
for proc, extra in [("ols", {}), ("batch", {}), ("batch0", {})]:
    rows_out = []
    P("  Verfahren %s gegen FCFS:" % proc)
    for d in DENS:
        a = ruf_cost_by_seed(ruf[ck(d)])
        b = ruf_cost_by_seed(ruf[ck(d, proc=proc)]) if ck(d, proc=proc) in ruf else None
        if b is None:
            continue
        sd = sorted(set(a) & set(b))
        diff = [b[s][0] - a[s][0] for s in sd]
        m, se, nn = mean_se(diff)
        less = sum(1 for x in diff if x < 0)
        more = sum(1 for x in diff if x > 0)
        same = sum(1 for x in diff if x == 0)
        sdiff = []
        for s in sd:
            Kf = a[s][0]
            rb = [r for r in ruf[ck(d, proc=proc)][s] if r["K"] == Kf]
            ra = [r for r in ruf[ck(d)][s] if r["K"] == Kf]
            if rb and ra:
                sdiff.append(rb[0]["served"] - ra[0]["served"])
        sm_, sse, _ = mean_se(sdiff)
        rec = dict(dens=d, K_fcfs=float(np.mean([a[s][0] for s in sd])), K_proc=float(np.mean([b[s][0] for s in sd])), diff_mean=m, diff_se=se, less=less, more=more, same=same,
                   served_diff_at_Kfcfs=sm_, served_diff_se=sse)
        rows_out.append(rec)
        P("    d=%.2f K*: FCFS %.2f, %s %.2f; Differenz %+.2f ± %.2f (%d Seeds weniger, %d gleich, %d mehr); Servicegrad bei K*_FCFS: %+.3f ± %.3f" % (
            d, rec["K_fcfs"], proc, rec["K_proc"], m, se, less, same, more, sm_, sse))
    proc_tab[proc] = rows_out
R["proc_vs_fcfs"] = proc_tab

P("\n  Batch-Fenster B (c=4, f=1.5), Dichten 0.2/0.4/0.8: K*-Differenz zu FCFS")
batchB = {}
for B in (2.0, 5.0, 10.0):
    for d in (0.2, 0.4, 0.8):
        key = (10.0, 50, 15.0, B, 30, 4, 1.5, "batch", d, 0)
        a = ruf_cost_by_seed(ruf[ck(d)])
        b = ruf_cost_by_seed(ruf[key])
        sd = sorted(set(a) & set(b))
        diff = [b[s][0] - a[s][0] for s in sd]
        m, se, _ = mean_se(diff)
        batchB[(B, d)] = (m, se)
        P("    B=%g d=%.1f: %+.2f ± %.2f (K*_FCFS %.2f)" % (B, d, m, se, np.mean([a[s][0] for s in sd])))
R["batchB"] = {"%g_%g" % k: v for k, v in batchB.items()}

P("\n  Rauschgrenze: Batch-Suche mit zweitem Suchzufall (ss=1) gegen ss=0, gleiche Instanzen")
noise = {}
allk = []
alls = []
for d in (0.2, 0.4, 0.8):
    a = ruf_cost_by_seed(ruf[ck(d, proc="batch")])
    b = ruf_cost_by_seed(ruf[ck(d, proc="batch", ss=1)])
    sd = sorted(set(a) & set(b))
    dk = [abs(a[s][0] - b[s][0]) for s in sd]
    ds = []
    for s in sd:
        Kf = a[s][0]
        ra = [r for r in ruf[ck(d, proc="batch")][s] if r["K"] == Kf]
        rb = [r for r in ruf[ck(d, proc="batch", ss=1)][s] if r["K"] == Kf]
        if ra and rb:
            ds.append(abs(ra[0]["served"] - rb[0]["served"]))
    allk += dk
    alls += ds
    noise[d] = dict(K_mean_absdiff=float(np.mean(dk)), K_p95=q(dk, .95), K_zero_share=float(np.mean([x == 0 for x in dk])), served_p95=q(ds, .95))
    P("    d=%.1f: |K*(ss0)-K*(ss1)| Mittel %.2f, P95 %.1f, identisch in %.0f %% der Seeds; |Servicegrad(ss0)-(ss1)| bei gleichem K: P95 %.3f" % (
        d, noise[d]["K_mean_absdiff"], noise[d]["K_p95"], 100 * noise[d]["K_zero_share"], noise[d]["served_p95"]))
R["noise"] = {str(k): v for k, v in noise.items()}
R["noise_all"] = dict(K_p95=q(allk, .95), served_p95=q(alls, .95), n=len(allk))
P("    alle Dichten: P95 der K*-Differenz %.1f, P95 der Servicegrad-Differenz %.3f (n=%d)" % (R["noise_all"]["K_p95"], R["noise_all"]["served_p95"], len(allk)))

# ------------------------------------------------------------------------------ 5. Bündelung
P("\n=== 5. Bündelung bei K* (c=4/8, f=1,5/2, FCFS): Anteil Fahrgäste mit Mitfahrern, mittlere Mitfahrer, Besetzung")
pool = []
for d in DENS:
    rowp = {"dens": d}
    for c, f in [(4, 1.5), (8, 1.5), (4, 2.0)]:
        rc = ruf_cost_by_seed(ruf[ck(d, c=c, f=f)])
        rs = [rc[s][2] for s in sorted(rc)]
        rowp["c%d_f%.1f" % (c, f)] = dict(shared=float(np.mean([r["shared"] for r in rs])), corider=float(np.mean([r["corider"] for r in rs])),
                                           occ=float(np.mean([r["occ"] for r in rs])), K=float(np.mean([rc[s][0] for s in rc])))
    pool.append(rowp)
    P("  d=%.2f " % d + " | ".join("c=%d f=%.1f: shared %.2f corider %.2f occ %.2f" % (c, f, rowp["c%d_f%.1f" % (c, f)]["shared"], rowp["c%d_f%.1f" % (c, f)]["corider"], rowp["c%d_f%.1f" % (c, f)]["occ"]) for c, f in [(4, 1.5), (8, 1.5), (4, 2.0)]))
R["pooling"] = pool

P("\n  Wirkung von Kapazität und Umwegfaktor auf K* (FCFS, gepaart gegen c=4,f=1.5)")
capf = []
for d in DENS:
    a = ruf_cost_by_seed(ruf[ck(d)])
    rec = {"dens": d}
    for c, f in [(8, 1.5), (4, 2.0), (8, 2.0)]:
        b = ruf_cost_by_seed(ruf[ck(d, c=c, f=f)])
        diff = [b[s][0] - a[s][0] for s in sorted(a)]
        m, se, _ = mean_se(diff)
        rec["c%d_f%.1f" % (c, f)] = (m, se, sum(1 for x in diff if x != 0))
    for c in (1, 2, 3):
        key = ck(d, c=c)
        if key in ruf:
            b = ruf_cost_by_seed(ruf[key])
            diff = [b[s][0] - a[s][0] for s in sorted(a)]
            m, se, _ = mean_se(diff)
            rec["c%d_f1.5" % c] = (m, se, sum(1 for x in diff if x != 0))
    capf.append(rec)
    P("  d=%.2f " % d + "  ".join("%s: %+.2f ± %.2f (%d/30 Seeds abweichend)" % (k, v[0], v[1], v[2]) for k, v in rec.items() if k != "dens"))
R["cap_f"] = capf

P("\n  Wirkung der Bündelung auf die Mindestflotte: K* mit c=1 (kein Mitfahren), c=2, c=4, c=8 (FCFS, f=1.5)")
pool_eff = []
for d in DENS:
    rec = {"dens": d}
    for c in (1, 2, 4, 8):
        rc = ruf_cost_by_seed(ruf[ck(d, c=c)])
        rec["K_c%d" % c] = float(np.mean([rc[s][0] for s in rc]))
        rec["cost_c%d" % c] = float(np.mean([rc[s][1] for s in rc]))
    rec["saving_c4_vs_c1"] = 1 - rec["K_c4"] / rec["K_c1"]
    pool_eff.append(rec)
    P("  d=%.2f K*: c=1 %.2f, c=2 %.2f, c=4 %.2f, c=8 %.2f  -> Bündelung (c=4 gegen c=1) spart %.0f %% der Flotte; vh/Pax c=1 %.3f, c=4 %.3f" % (
        d, rec["K_c1"], rec["K_c2"], rec["K_c4"], rec["K_c8"], 100 * rec["saving_c4_vs_c1"], rec["cost_c1"], rec["cost_c4"]))
R["pool_effect"] = pool_eff

# ------------------------------------------------------------------------------ 6. Servicegrad-Kosten-Kurven
P("\n=== 6. Servicegrad gegen Flotte (Rufbus FCFS c=4 f=1,5) und gegen N (Linienbus R, S2): Mittel ± SE über 30 Seeds")
curves = {}
for d in (0.06, 0.20, 0.60):
    cell = ruf[ck(d)]
    byK = collections.defaultdict(list)
    for s, rows in cell.items():
        for r in rows:
            byK[r["K"]].append(r["served"])
    Ks = sorted(byK)
    txtR = " ".join("K=%d:%.2f" % (k, np.mean(byK[k])) + ("(%d)" % len(byK[k]) if len(byK[k]) < 30 else "") for k in Ks)
    P("  Rufbus d=%.2f: %s" % (d, txtR))
    curves["ruf_%g" % d] = {k: (float(np.mean(byK[k])), mean_se(byK[k])[1], len(byK[k])) for k in Ks}
    for dd in ("R", "S2"):
        byN = collections.defaultdict(list)
        byNw = collections.defaultdict(list)
        for s in sorted(cell):
            res = line[(10.0, 50, 30, s, d)][dd]
            for N, v in res.items():
                if v is None:
                    continue
                byN[N].append(v["env_25_2"])
                byNw[N].append(v.get("wait", float("nan")))
        sel = [n_ for n_ in sorted(byN) if n_ in (2, 4, 6, 8, 10, 12, 14, 16, 20, 24, 30)]
        P("  Linienbus %s d=%.2f (Anteil im Rahmen W=25,f=2): " % (dd, d) + " ".join("N=%d:%.2f(w%.0f)" % (n_, np.mean(byN[n_]), np.nanmean(byNw[n_])) for n_ in sel))
        curves["line_%s_%g" % (dd, d)] = {n_: (float(np.mean(byN[n_])), float(np.nanmean(byNw[n_]))) for n_ in sorted(byN)}
R["curves"] = {k: {str(a): b for a, b in v.items()} for k, v in curves.items()}

# ------------------------------------------------------------------------------ 7. Exakt
P("\n=== 7. Kleine Instanzen: Heuristiken gegen exakten Referenzwert")
ex_rows = [json.loads(l) for l in open(os.path.join(DATA, "exact.jsonl"), encoding="utf-8")]
grp = collections.defaultdict(list)
for r in ex_rows:
    grp[(r["n"], r["K"], r["span"], r["W"])].append(r)
ex_tab = {}
for k in sorted(grp):
    v = grp[k]
    n = len(v)
    rec = dict(n_inst=n, complete=sum(1 for r in v if r["ex_complete"]))
    for nm in ("fcfs", "batch", "off"):
        sv = [r["ex_served"] - r[nm + "_served"] for r in v]
        same_served = [r for r in v if r[nm + "_served"] == r["ex_served"]]
        optimal = [r for r in same_served if r[nm + "_cost"] <= r["ex_cost"] + 1e-6]
        cgap = [(r[nm + "_cost"] - r["ex_cost"]) / r["ex_cost"] for r in same_served if r["ex_cost"] > 0]
        rec[nm] = dict(served_gap_mean=float(np.mean(sv)), served_gap_se=mean_se(sv)[1], share_all_served_as_exact=len(same_served) / n,
                       share_optimal=len(optimal) / n, cost_gap_mean_pct=100 * float(np.mean(cgap)) if cgap else None, cost_gap_p90_pct=100 * q(cgap, .9) if cgap else None,
                       time_median_ms=1000 * q([r[nm + "_time"] for r in v], .5))
        rec[nm]["served_rel"] = float(np.mean([r[nm + "_served"] for r in v]) / np.mean([r["ex_served"] for r in v]))
    rec["ex_time_median_ms"] = 1000 * q([r["ex_time"] for r in v], .5)
    rec["ex_time_max_s"] = max(r["ex_time"] for r in v)
    rec["ex_served_mean"] = float(np.mean([r["ex_served"] for r in v]))
    ex_tab["%d_%d_%g_%g" % k] = rec
    P("  n=%d K=%d %s W=%g (%d Inst., exakt vollständig %d): exakt bedient %.2f von %d; " % (k[0], k[1], "Los(alle gleichzeitig)" if k[2] == 0 else "Fenster %g min" % k[2], k[3], n, rec["complete"], rec["ex_served_mean"], k[0]) +
      " | ".join("%s: %.0f %% des Exakten bedient, gleich viele wie exakt in %.0f %% (davon kostenoptimal %.0f %%), Kostenlücke bei gleichem Servicegrad %s; %.1f ms" % (
          nm, 100 * rec[nm]["served_rel"], 100 * rec[nm]["share_all_served_as_exact"], 100 * rec[nm]["share_optimal"],
          ("%.1f %%" % rec[nm]["cost_gap_mean_pct"]) if rec[nm]["cost_gap_mean_pct"] is not None else "-", rec[nm]["time_median_ms"]) for nm in ("fcfs", "batch", "off")) +
      "; exakt Median %.1f ms, Max %.2f s" % (rec["ex_time_median_ms"], rec["ex_time_max_s"]))
R["exact"] = ex_tab

viol = 0
for r in ex_rows:
    for nm in ("fcfs", "batch", "off"):
        if r[nm + "_served"] > r["ex_served"] or (r[nm + "_served"] == r["ex_served"] and r[nm + "_cost"] < r["ex_cost"] - 1e-6):
            viol += 1
early_worse = sum(1 for r in ex_rows if "early_served" in r and (r["early_served"], -r["early_cost"]) > (r["ex_served"], -r["ex_cost"] + 1e-6))
early_better = sum(1 for r in ex_rows if "early_served" in r and (r["ex_served"], -r["ex_cost"]) > (r["early_served"], -r["early_cost"] + 1e-6))
n_early = sum(1 for r in ex_rows if "early_served" in r)
R["exact_checks"] = dict(heur_beats_exact=viol, rows=len(ex_rows), early_better_than_flex=early_worse, flex_better_than_early=early_better, n=n_early,
                         incomplete=sum(1 for r in ex_rows if not r["ex_complete"]))
P("  Prüfung: Heuristik schlägt den exakten Wert in %d von %d Vergleichen (muss 0 sein); exakte Aufzählung unvollständig (Knotengrenze): %d Instanzen" % (viol, 3 * len(ex_rows), R["exact_checks"]["incomplete"]))
P("  exakt mit freiem Abwarten gegen exakt ohne freiwilliges Abwarten: mit Abwarten besser in %d von %d Instanzen, nie schlechter (%d)" % (early_better, n_early, early_worse))

need = {}
for W_ in (15.0, 30.0):
    bys = collections.defaultdict(dict)
    for r in ex_rows:
        if r["span"] == 0.0 and r["n"] == 8 and r["W"] == W_:
            bys[r["seed"]][r["K"]] = r
    res_ = {nm: [] for nm in ("ex", "fcfs", "batch", "off")}
    for sd_, d_ in bys.items():
        if sorted(d_) != [1, 2, 3]:
            continue
        for nm in res_:
            Kmin = next((K_ for K_ in (1, 2, 3) if d_[K_][nm + "_served"] >= d_[K_]["n"]), 4)
            res_[nm].append(Kmin)
    need[W_] = {nm: dict(mean=float(np.mean(v)), n=len(v), over_exact=sum(1 for a_, b_ in zip(v, res_["ex"]) if a_ > b_)) for nm, v in res_.items() if v}
    P("  Los von 8 Anfragen, W=%g: nötige Fahrzeuge (1..3, 4 = auch 3 reichen nicht), Mittel: " % W_ + ", ".join("%s %.2f (mehr als exakt in %d von %d Losen)" % (nm, v["mean"], v["over_exact"], v["n"]) for nm, v in need[W_].items()))
R["exact_need"] = {str(k): v for k, v in need.items()}

# ------------------------------------------------------------------------------ 8. Zähler
P("\n=== 8. Zähler Verbesserungsschritte (Summe über alle Läufe)")
cnt_tab = {}
for proc in ("fcfs", "ols", "batch", "batch0"):
    tot_ = collections.Counter()
    nrun = 0
    for key, cell in ruf.items():
        if key[7] != proc:
            continue
        for s, rows in cell.items():
            for r in rows:
                nrun += 1
                for k_, v in r["cnt"].items():
                    tot_[k_] += v
    cnt_tab[proc] = dict(tot_, runs=nrun)
    P("  %-7s Läufe %6d: %s" % (proc, nrun, dict(tot_)))
R["counters"] = cnt_tab

# ------------------------------------------------------------------------------ 9. Meta
cpu_ruf = sum(r["time_s"] for c in ruf.values() for rows in c.values() for r in rows)


def wallclock(fn):
    p = os.path.join(DATA, fn)
    try:
        return float(open(p).read().strip())
    except OSError:
        return None


n_line_rows = sum(len(v) for v in line.values())
R["meta"] = dict(
    n_runs=n_runs, n_cells=len(ruf), seeds_per_cell=dict(seeds_per_cell), n_line_rows=n_line_rows, n_exact_instances=len(ex_rows),
    cpu_time_ruf_runs_s=cpu_ruf, wallclock_s=dict(ruf=wallclock("sweep_ruf_wallclock.txt"), line=wallclock("sweep_line_wallclock.txt"), exact=wallclock("sweep_exact_wallclock.txt")),
    python=platform.python_version(), numpy=np.__version__, date=datetime.date.today().isoformat(),
    seeds=[1, 30], dens=DENS, bootstrap=dict(n=BOOT_N, seed=BOOT_SEED, generator="numpy.random.default_rng"),
    generator="ganzzahlig (SplitMix64, ruf_network.World), Raster 5..95")
P("\nMeta:", R["meta"])


# ------------------------------------------------------------------------------ Schreiben
def clean(o):
    if isinstance(o, dict):
        return {(k if isinstance(k, str) else str(k)): clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [clean(v) for v in o]
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating, float)):
        f_ = float(o)
        return f_ if not math.isnan(f_) else None   # +-inf bleibt erhalten (Python-JSON schreibt Infinity), NaN wird null
    if isinstance(o, np.ndarray):
        return clean(o.tolist())
    return o


with open(OUTJ, "w", encoding="utf-8") as fh:
    json.dump(clean(R), fh, indent=1, ensure_ascii=False)
with open(OUTT, "w", encoding="utf-8") as fh:
    fh.write("\n".join(TXT) + "\n")
print("geschrieben:", OUTJ)
