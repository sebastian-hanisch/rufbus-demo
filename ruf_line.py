"""Linienbus-Seite: Liniennetze (Pfadlinie über alle Haltepunkte, Sternnetz mit m Linien durch den Hub, Teilabdeckung mit Fußweg), Fahrplan,
erwartungswertbasierte Wegewahl (Dijkstra mit Wartezeit h/2 je Einstieg, 1 min Umstieg) und Auswertung der realisierten Fahrgastzeiten
gegen einen echten periodischen Fahrplan. Nur numpy + heapq.

Entscheidungen über Reihenfolgen (Winkel um den Hub, Schwerpunkt, Abdeckungsanteil) laufen über Ganzzahlen (Rasterkoordinaten), nicht über
`arctan2` oder Gleitkomma-Summen, damit die Entwürfe auf jeder Plattform dieselben sind."""
import heapq
import math
from functools import cmp_to_key

import numpy as np

from ruf_constants import CAP_LINE, DWELL, LAYOVER, SLACK, TRANSFER, WALK_KMH  # noqa: F401

DESIGNS = ["R", "S1", "S2", "S3", "S4", "P1", "P2"]
PARTIAL_RADIUS = {"P1": 1.0, "P2": 1.5}   # km Fußweg zur Linie
PARTIAL_COVER_PCT = 97                     # Prozent des Nachfragegewichts, dessen beide Enden im Einzugsbereich liegen sollen
ENVELOPES = [(10.0, 1.5), (15.0, 1.5), (15.0, 2.0), (25.0, 2.0), (40.0, 2.0)]


def tsp_path(world, subset=None):
    """Pfad über die Haltepunkte: Start am weitesten vom Schwerpunkt (ganzzahlig verglichen), nächster Nachbar, dann 2-opt."""
    D = world.dist
    nodes = list(range(world.n)) if subset is None else list(subset)
    n = len(nodes)
    sx = sum(int(world.grid[i][0]) for i in nodes)
    sy = sum(int(world.grid[i][1]) for i in nodes)

    def far(i):
        return (n * int(world.grid[i][0]) - sx) ** 2 + (n * int(world.grid[i][1]) - sy) ** 2

    start = max(nodes, key=lambda i: (far(i), -i))
    path = [start]
    left = set(nodes) - {start}
    while left:
        last = path[-1]
        nxt = min(left, key=lambda j: (D[last, j], j))
        path.append(nxt)
        left.remove(nxt)
    improved = True
    while improved:
        improved = False
        for i in range(0, n - 1):
            for k in range(i + 1, n):
                # Segment path[i..k] umdrehen
                a = D[path[i - 1], path[i]] if i > 0 else 0.0
                b = D[path[k], path[k + 1]] if k < n - 1 else 0.0
                a2 = D[path[i - 1], path[k]] if i > 0 else 0.0
                b2 = D[path[i], path[k + 1]] if k < n - 1 else 0.0
                if a2 + b2 < a + b - 1e-9:
                    path[i:k + 1] = path[i:k + 1][::-1]
                    improved = True
    return path


def _angle_order(world, hub, others):
    """Haltepunkte nach Winkel um den Hub von -pi (ausschließlich) bis +pi, rein ganzzahlig (Halbebene, dann Kreuzprodukt, dann Index)."""
    gx, gy = int(world.grid[hub][0]), int(world.grid[hub][1])
    vec = {i: (int(world.grid[i][0]) - gx, int(world.grid[i][1]) - gy) for i in others}

    def half(v):
        dx, dy = v
        if dy < 0:
            return 0
        if dy == 0 and dx >= 0:
            return 1
        if dy > 0:
            return 2
        return 3

    def cmp(a, b):
        va, vb = vec[a], vec[b]
        ha, hb = half(va), half(vb)
        if ha != hb:
            return -1 if ha < hb else 1
        cross = va[0] * vb[1] - va[1] * vb[0]
        if cross != 0 and ha in (0, 2):
            return -1 if cross > 0 else 1
        return -1 if a < b else (1 if a > b else 0)

    return sorted(others, key=cmp_to_key(cmp))


def _split(items, parts):
    """Wie np.array_split: die ersten len % parts Teile bekommen ein Element mehr."""
    q, r = divmod(len(items), parts)
    out, pos = [], 0
    for k in range(parts):
        size = q + (1 if k < r else 0)
        out.append(items[pos:pos + size])
        pos += size
    return out


def star_lines(world, m):
    hub = world.hub
    others = [i for i in range(world.n) if i != hub]
    order = _angle_order(world, hub, others)
    chunks = _split(order, 2 * m)
    d = world.dist[hub]
    lines = []
    for l in range(m):
        a = sorted(chunks[l], key=lambda s: (-d[s], s))
        b = sorted(chunks[l + m], key=lambda s: (d[s], s))
        lines.append(a + [hub] + b)
    return lines


def partial_design(world, radius):
    """Teilabdeckung: wenige Linienhaltestellen, restliche Haltepunkte per Fußweg (<= radius km). Rückgabe (Linienhalte, acc, walk_min)."""
    n = world.n
    dist = world.dist
    wgt = [[int(v) for v in row] for row in world.demand]
    total = sum(sum(r) for r in wgt)
    chosen = []
    covered = [False] * n

    def cov_num(cv):
        idx = [i for i in range(n) if cv[i]]
        return sum(wgt[i][j] for i in idx for j in idx)

    def cover_with(cv, c_):
        return [cv[i] or bool(dist[c_, i] <= radius + 1e-9) for i in range(n)]

    while 100 * cov_num(covered) < PARTIAL_COVER_PCT * total and len(chosen) < n:
        best = None
        for c_ in range(n):
            if c_ in chosen:
                continue
            gain = cov_num(cover_with(covered, c_))
            if best is None or gain > best[0]:
                best = (gain, c_)
        chosen.append(best[1])
        covered = cover_with(covered, best[1])
    acc = np.full(n, -1, dtype=int)
    walk = np.zeros(n)
    for i in range(n):
        j = min(chosen, key=lambda c_: (dist[i, c_], c_))
        if dist[i, j] <= radius + 1e-9:
            acc[i] = j
            walk[i] = dist[i, j] / WALK_KMH * 60.0
    return tsp_path(world, chosen), acc, walk

def design_lines(world, design):
    if design == "R":
        return [tsp_path(world)]
    if design in PARTIAL_RADIUS:
        return [partial_design(world, PARTIAL_RADIUS[design])[0]]
    m = int(design[1])
    return star_lines(world, m)


def design_access(world, design):
    if design in PARTIAL_RADIUS:
        _, acc, walk = partial_design(world, PARTIAL_RADIUS[design])
        return acc, walk
    return None


class Line:
    def __init__(self, world, stops):
        tt = world.tt
        self.stops = [int(s) for s in stops]
        P = len(self.stops)
        self.P = P
        seg = [tt[self.stops[q]][self.stops[q + 1]] + DWELL for q in range(P - 1)]
        self.seg = seg
        self.tauf = [0.0]
        for q in range(P - 1):
            self.tauf.append(self.tauf[-1] + seg[q])
        T1 = self.tauf[-1]
        taub = [0.0] * P
        taub[P - 1] = T1 + LAYOVER
        for q in range(P - 2, -1, -1):
            taub[q] = taub[q + 1] + seg[q]
        self.taub = taub
        self.C = taub[0] + LAYOVER


def alloc_vehicles(Cs, N):
    m = len(Cs)
    if N < m:
        return None
    Nl = [1] * m
    for _ in range(N - m):
        k = max(range(m), key=lambda l: (Cs[l] / Nl[l], -l))
        Nl[k] += 1
    return Nl


def route_table(world, lines, Nl):
    """Erwartungswertbasierte Wege: für jedes Paar (o,d) bis zu 3 Teilstrecken (Linie, Pos Einstieg, Pos Ausstieg)."""
    n = world.n
    tt = world.tt
    m = len(lines)
    h = [lines[l].C / Nl[l] for l in range(m)]
    off = []
    tot = n
    for l in range(m):
        off.append(tot)
        tot += lines[l].P
    # Kanten
    adj = [[] for _ in range(tot)]
    for l, ln in enumerate(lines):
        for p, s in enumerate(ln.stops):
            node = off[l] + p
            adj[s].append((node, h[l] / 2.0 + 0.0, 1))     # Einstieg
            adj[node].append((s, 0.0, 2))                 # Ausstieg
            if p + 1 < ln.P:
                w = ln.seg[p]
                adj[node].append((node + 1, w, 0))
                adj[node + 1].append((node, w, 0))
    LEG = np.full((n, n, 3, 3), -1, dtype=np.int32)
    EXP = np.full((n, n), np.inf)
    for o in range(n):
        dist = [math.inf] * tot
        pred = [-1] * tot
        dist[o] = 0.0
        pq = [(0.0, o)]
        while pq:
            dd, u = heapq.heappop(pq)
            if dd > dist[u] + 1e-12:
                continue
            for v, w, kind in adj[u]:
                nd = dd + w
                if kind == 1 and u != o:
                    nd += TRANSFER      # Umstieg: Weg zum Bahnsteig
                if nd < dist[v] - 1e-12:
                    dist[v] = nd
                    pred[v] = u
                    heapq.heappush(pq, (nd, v))
        for d in range(n):
            if d == o or not math.isfinite(dist[d]):
                continue
            EXP[o, d] = dist[d]
            # Weg rekonstruieren
            seq = []
            x = d
            while x != -1:
                seq.append(x)
                x = pred[x]
            seq.reverse()
            legs = []
            cur = None
            for x in seq:
                if x >= n:
                    l = max(ll for ll in range(m) if off[ll] <= x)
                    p = x - off[l]
                    if cur is None or cur[0] != l:
                        cur = [l, p, p]
                        legs.append(cur)
                    else:
                        cur[2] = p
                else:
                    cur = None
            if len(legs) > 3:
                legs = legs[:3]
            for k, (l, pa, pe) in enumerate(legs):
                LEG[o, d, k] = (l, pa, pe)
    return LEG, EXP, h


def evaluate(world, lines, Nl, LEG, h, reqs, phases, t0, t1, access=None):
    """Realisierte Zeiten für die Anfragen im Messfenster. Rückgabe: dict von Arrays + Lastfaktor."""
    t = np.array([r[0] for r in reqs])
    o = np.array([r[1] for r in reqs], dtype=int)
    d = np.array([r[2] for r in reqs], dtype=int)
    sel = (t >= t0) & (t < t1)
    t, o, d = t[sel], o[sel], d[sel]
    n = len(t)
    m = len(lines)
    o_orig, d_orig = o.copy(), d.copy()
    walk_o = np.zeros(n)
    walk_d = np.zeros(n)
    acc_ok = np.ones(n, dtype=bool)
    if access is not None and n:
        acc, walk = access
        ol, dl = acc[o], acc[d]
        acc_ok = (ol >= 0) & (dl >= 0) & (ol != dl)
        walk_o = walk[o]
        walk_d = walk[d]
        o = np.where(acc_ok, ol, 0)
        d = np.where(acc_ok, dl, 1)
    cur = t + walk_o
    wait = np.zeros(n)
    ride = np.zeros(n)
    transf = np.zeros(n)
    ok = acc_ok.copy()
    if n == 0:
        return dict(n=0)
    L0 = LEG[o, d, 0, 0]
    ok &= L0 >= 0
    flow = [np.zeros((2, ln.P + 1)) for ln in lines]
    for k in range(3):
        lk = LEG[o, d, k, 0]
        pa = LEG[o, d, k, 1]
        pe = LEG[o, d, k, 2]
        if k > 0:
            cur = np.where(lk >= 0, cur + TRANSFER, cur)
            transf += (lk >= 0) * TRANSFER
        for l in range(m):
            msk = lk == l
            if not msk.any():
                continue
            ln = lines[l]
            tauf = np.array(ln.tauf)
            taub = np.array(ln.taub)
            a = pa[msk]
            e = pe[msk]
            fwd = e > a
            tau_a = np.where(fwd, tauf[a], taub[a])
            tau_e = np.where(fwd, tauf[e], taub[e])
            rd = tau_e - tau_a
            base = phases[l] + tau_a
            c = cur[msk]
            board = base + h[l] * np.ceil((c - base) / h[l] - 1e-12)
            wait[msk] += board - c
            ride[msk] += rd
            cur[msk] = board + rd
            for dirn, mm in ((0, fwd), (1, ~fwd)):
                lo = np.minimum(a, e)[mm]
                hi = np.maximum(a, e)[mm]
                np.add.at(flow[l][dirn], lo, 1)
                np.add.at(flow[l][dirn], hi, -1)
    total = cur + walk_d - t
    direct = np.array([world.tt[a][b] + DWELL for a, b in zip(o_orig, d_orig)])
    # Lastfaktor: Fahrgäste je Abschnitt und Richtung im Fenster gegen angebotene Plätze
    rho = 0.0
    dur = t1 - t0
    for l in range(m):
        fl = np.cumsum(flow[l], axis=1)[:, :-1]
        cap = CAP_LINE * dur / h[l]
        rho = max(rho, float(fl.max()) / cap)
    return dict(n=n, ok=ok, total=total, wait=wait, ride=ride, transf=transf, direct=direct, rho=rho, walk=walk_o + walk_d)


def summarize_line(res, envs=ENVELOPES):
    n = res["n"]
    if n == 0:
        return None
    ok = res["ok"]
    out = {"reach": float(ok.mean()), "rho": res["rho"]}
    tot, direct = res["total"], res["direct"]
    for W, f in envs:
        inside = ok & (tot <= W + f * direct + SLACK + 1e-9)
        out["env_%g_%g" % (W, f)] = float(inside.mean())
    if ok.any():
        out["wait"] = float(res["wait"][ok].mean())
        out["ride"] = float(res["ride"][ok].mean())
        out["total"] = float(tot[ok].mean())
        out["transfer_share"] = float((res["transf"][ok] > 0).mean())
        out["walk"] = float(res["walk"][ok].mean())
        out["total_p90"] = float(np.quantile(tot[ok], 0.9))
    return out
