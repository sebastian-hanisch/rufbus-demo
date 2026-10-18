"""Allgemeiner Routenbewerter (mit Warten auf die Anfragezeit), exakte Aufzählung für kleine Instanzen,
Offline-Einfügeheuristik. Unabhängig von der schnellen Einfügelogik in ruf_sim.py geschrieben."""
import itertools

from ruf_constants import EPS

INF = float("inf")


def sim_route(loc0, t0, events, rel, ddl, rmax, tt, dw, cap, onboard_pick=None):
    """Zeitlicher Ablauf einer Route ohne freiwilliges Warten (nur Warten bis zur Anfragezeit bei Abholungen).
    events: Liste (stop, req, isdrop). Rückgabe None (unzulässig) oder (Endzeit, Fahr+Haltezeit, picks)."""
    onboard_pick = onboard_pick or {}
    t, loc = t0, loc0
    load = len(onboard_pick)
    picks = {}
    busy = 0.0
    for s, r, isd in events:
        a = t + tt[loc][s]
        if not isd:
            if a < rel[r]:
                a = rel[r]
            if a > ddl[r] + EPS:
                return None
            picks[r] = a
            load += 1
            if load > cap:
                return None
        else:
            p = picks.get(r, onboard_pick.get(r))
            if p is None:
                return None
            if a - p > rmax[r] + EPS:
                return None
            load -= 1
        busy += tt[loc][s] + dw
        t = a + dw
        loc = s
    return (t, busy, picks)


def brute_insert(loc0, t0, events, new, rel, ddl, rmax, tt, dw, cap, onboard_pick, first_index, ro, rd):
    """Alle (i,j) durchprobieren; Rückgabe dict {(i,j): Kosten} der zulässigen. Kosten = Endzeit neu - Endzeit alt."""
    base = sim_route(loc0, t0, events, rel, ddl, rmax, tt, dw, cap, onboard_pick)
    assert base is not None
    old_end = base[0] if events else t0
    out = {}
    m = len(events)
    for i in range(first_index, m + 1):
        for j in range(i, m + 1):
            ev = events[:i] + [(ro[new], new, False)] + events[i:j] + [(rd[new], new, True)] + events[j:]
            res = sim_route(loc0, t0, ev, rel, ddl, rmax, tt, dw, cap, onboard_pick)
            if res is not None:
                out[(i, j)] = res[0] - old_end
    return out


# ---------------------------------------------------------------------------- exakt
def exact_vehicle_table(start, rel, ddl, rmax, ro, rd, tt, dw, cap, n, node_limit=4_000_000):
    """best[S] = minimale Fahr+Haltezeit einer zulässigen Route, die genau die Menge S (Bitmaske) bedient. DFS."""
    best = {0: 0.0}
    nodes = [0]
    complete = [True]
    full_pick = [0.0] * n

    def dfs(t, loc, load, onboard, picked, cost):
        nodes[0] += 1
        if nodes[0] > node_limit:
            complete[0] = False
            return
        if onboard == 0 and picked:
            if cost < best.get(picked, INF) - EPS:
                best[picked] = cost
        for r in range(n):
            bit = 1 << r
            if picked & bit:
                if onboard & bit:
                    a = t + tt[loc][rd[r]]
                    if a - full_pick[r] <= rmax[r] + EPS:
                        dfs(a + dw, rd[r], load - 1, onboard & ~bit, picked, cost + tt[loc][rd[r]] + dw)
            else:
                if load + 1 > cap:
                    continue
                a = t + tt[loc][ro[r]]
                if a < rel[r]:
                    a = rel[r]
                if a > ddl[r] + EPS:
                    continue
                old = full_pick[r]
                full_pick[r] = a
                dfs(a + dw, ro[r], load + 1, onboard | bit, picked | bit, cost + tt[loc][ro[r]] + dw)
                full_pick[r] = old

    dfs(0.0, start, 0, 0, 0, 0.0)
    return best, complete[0], nodes[0]


def exact_solve(starts, rel, ddl, rmax, ro, rd, tt, dw, cap, node_limit=4_000_000):
    """Lexikografisch: erst möglichst viele bedient, dann minimale Kosten (Fahr+Haltezeit). Rückgabe (served, cost, complete)."""
    n = len(rel)
    tabs = []
    complete = True
    for s in starts:
        b, c, _ = exact_vehicle_table(s, rel, ddl, rmax, ro, rd, tt, dw, cap, n, node_limit)
        tabs.append(b)
        complete &= c
    g = {0: 0.0}
    for b in tabs:
        ng = dict(g)
        for M, cm in g.items():
            for S, cs in b.items():
                if S & M:
                    continue
                U = M | S
                v = cm + cs
                if v < ng.get(U, INF) - EPS:
                    ng[U] = v
        g = ng
    best = None
    for M, c in g.items():
        key = (-bin(M).count("1"), round(c, 9))
        if best is None or key < best[0]:
            best = (key, M)
    return -best[0][0], best[0][1], complete


def exact_by_permutations(starts, rel, ddl, rmax, ro, rd, tt, dw, cap):
    """Unabhängige Kontrolle für n<=4, K<=2: alle Zuordnungen und alle Ereignisreihenfolgen."""
    n = len(rel)
    K = len(starts)
    best = None
    for assign in itertools.product(range(K + 1), repeat=n):
        total = 0.0
        ok = True
        served = 0
        for v in range(K):
            reqs = [r for r in range(n) if assign[r] == v]
            if not reqs:
                continue
            events = []
            for r in reqs:
                events.append((ro[r], r, False))
                events.append((rd[r], r, True))
            bestv = INF
            for perm in itertools.permutations(events):
                pos = {}
                bad = False
                for k, (s, r, isd) in enumerate(perm):
                    if isd and (r not in pos):
                        bad = True
                        break
                    pos[r] = k
                if bad:
                    continue
                res = sim_route(starts[v], 0.0, list(perm), rel, ddl, rmax, tt, dw, cap)
                if res is not None and res[1] < bestv:
                    bestv = res[1]
            if bestv == INF:
                ok = False
                break
            total += bestv
            served += len(reqs)
        if not ok:
            continue
        key = (-served, round(total, 9))
        if best is None or key < best:
            best = key
    return -best[0], best[1]


# ---------------------------------------------------------------------------- Offline-Heuristik
def offline_heuristic(starts, rel, ddl, rmax, ro, rd, tt, dw, cap, improve=True):
    """Alle Anfragen vorab bekannt; Regret-Einfügen mit vollständiger Positionsaufzählung, dann Umlegen bis keine Verbesserung."""
    n = len(rel)
    K = len(starts)
    routes = [[] for _ in range(K)]

    def cost_of(v, ev):
        res = sim_route(starts[v], 0.0, ev, rel, ddl, rmax, tt, dw, cap)
        return None if res is None else res[1]

    def best_pos(v, r, route):
        base = cost_of(v, route) if route else 0.0
        if base is None:
            return None
        best = None
        for i in range(len(route) + 1):
            for j in range(i, len(route) + 1):
                ev = route[:i] + [(ro[r], r, False)] + route[i:j] + [(rd[r], r, True)] + route[j:]
                c = cost_of(v, ev)
                if c is not None and (best is None or c - base < best[0] - EPS):
                    best = (c - base, ev)
        return best

    un = list(range(n))
    rejected = []
    while un:
        choice = None
        for r in list(un):
            cands = []
            for v in range(K):
                b = best_pos(v, r, routes[v])
                if b is not None:
                    cands.append((b[0], v, b[1]))
            if not cands:
                un.remove(r)
                rejected.append(r)
                continue
            cands.sort(key=lambda x: (x[0], x[1]))
            regret = cands[1][0] - cands[0][0] if len(cands) > 1 else 1e6
            key = (-regret, cands[0][0], r)
            if choice is None or key < choice[0]:
                choice = (key, r, cands[0])
        if choice is None:
            break
        _, r, (c, v, ev) = choice
        routes[v] = ev
        un.remove(r)
    if improve:
        for _ in range(5):
            changed = False
            assigned = [r for v in range(K) for (s, r, isd) in routes[v] if not isd]
            for r in assigned:
                v = next(u for u in range(K) if any(e[1] == r for e in routes[u]))
                cur_total = sum(cost_of(u, routes[u]) or 0.0 for u in range(K) if routes[u])
                saved = [list(x) for x in routes]
                routes[v] = [e for e in routes[v] if e[1] != r]
                if routes[v] and cost_of(v, routes[v]) is None:
                    routes = saved
                    continue
                bestc, bestset = None, None
                for u in range(K):
                    b = best_pos(u, r, routes[u])
                    if b is not None:
                        tot = sum(cost_of(w, routes[w]) or 0.0 for w in range(K) if routes[w] and w != u) + (
                            cost_of(u, b[1]))
                        if bestc is None or tot < bestc - EPS:
                            bestc, bestset = tot, (u, b[1])
                if bestc is not None and bestc < cur_total - 1e-7:
                    routes[bestset[0]] = bestset[1]
                    changed = True
                else:
                    routes = saved
            for r in list(rejected):
                for v in range(K):
                    b = best_pos(v, r, routes[v])
                    if b is not None:
                        routes[v] = b[1]
                        rejected.remove(r)
                        changed = True
                        break
            if not changed:
                break
    served = n - len(rejected)
    cost = sum(cost_of(v, routes[v]) or 0.0 for v in range(K) if routes[v])
    return served, cost


def exact_solve2(starts, rel, ddl, rmax, ro, rd, tt, dw, cap, node_limit=4_000_000):
    """Wie exact_solve, gibt aber (bediente, Kosten, vollständig) zurück."""
    n = len(rel)
    tabs = []
    complete = True
    for s in starts:
        b, c, _ = exact_vehicle_table(s, rel, ddl, rmax, ro, rd, tt, dw, cap, n, node_limit)
        tabs.append(b)
        complete &= c
    g = {0: 0.0}
    for b in tabs:
        ng = dict(g)
        for M, cm in g.items():
            for S, cs in b.items():
                if S & M:
                    continue
                U = M | S
                v = cm + cs
                if v < ng.get(U, INF) - EPS:
                    ng[U] = v
        g = ng
    key = min((-bin(M).count("1"), round(c, 9)) for M, c in g.items())
    return -key[0], key[1], complete


# ---------------------------------------------------------------------------- exakt mit frei wählbaren Wartezeiten (STN)
def stn_feasible(start, evs, rel, ddl, rmax, tt, dw):
    """Zeitliche Zulässigkeit einer Ereignisfolge, wenn das Fahrzeug an jeder Stelle beliebig warten darf (freiwilliges Abwarten, spätere Abfahrt).
    Differenzbeschränkungen (Simple Temporal Network), Bellman-Ford von der Bezugszeit 0. evs: Liste (stop, req, isdrop)."""
    m = len(evs)
    if m == 0:
        return True
    edges = []   # (von, nach, Gewicht): x_nach - x_von <= Gewicht ; Knoten 0 = Bezugszeit, Knoten k+1 = Ereignis k
    prev_loc = start
    pos = {}
    for k, (s, r, isd) in enumerate(evs):
        node = k + 1
        w = tt[prev_loc][s] + (dw if k > 0 else 0.0)
        if k == 0:
            edges.append((node, 0, -w))          # t_0 >= tt[start][s_0]
        else:
            edges.append((node, node - 1, -w))   # t_k >= t_{k-1} + dw + tt
        if not isd:
            edges.append((node, 0, -rel[r]))     # t >= rel
            edges.append((0, node, ddl[r]))      # t <= ddl
            pos[r] = node
        else:
            edges.append((pos[r], node, rmax[r]))  # t_drop - t_pick <= rmax
        prev_loc = s
    dist = [0.0] * (m + 1)
    for it in range(m + 1):
        ch = False
        for a, b, w in edges:
            if dist[a] + w < dist[b] - 1e-9:
                dist[b] = dist[a] + w
                ch = True
        if not ch:
            return True
    return False


def exact_vehicle_table_flex(start, rel, ddl, rmax, ro, rd, tt, dw, cap, n, node_limit=3_000_000):
    """Wie exact_vehicle_table, aber mit freiem Abwarten (STN-Zulässigkeit). best[S] = minimale Fahr+Haltezeit."""
    best = {0: 0.0}
    nodes = [0]
    complete = [True]
    seq = []

    def dfs(loc, load, onboard, picked, cost):
        nodes[0] += 1
        if nodes[0] > node_limit:
            complete[0] = False
            return
        if onboard == 0 and picked:
            if cost < best.get(picked, INF) - EPS:
                best[picked] = cost
        for r in range(n):
            bit = 1 << r
            if picked & bit:
                if onboard & bit:
                    seq.append((rd[r], r, True))
                    if stn_feasible(start, seq, rel, ddl, rmax, tt, dw):
                        dfs(rd[r], load - 1, onboard & ~bit, picked, cost + tt[loc][rd[r]] + dw)
                    seq.pop()
            else:
                if load + 1 > cap:
                    continue
                seq.append((ro[r], r, False))
                if stn_feasible(start, seq, rel, ddl, rmax, tt, dw):
                    dfs(ro[r], load + 1, onboard | bit, picked | bit, cost + tt[loc][ro[r]] + dw)
                seq.pop()

    dfs(start, 0, 0, 0, 0.0)
    return best, complete[0], nodes[0]


def exact_solve_flex(starts, rel, ddl, rmax, ro, rd, tt, dw, cap, node_limit=3_000_000):
    n = len(rel)
    tabs = []
    complete = True
    nodes = 0
    for s in starts:
        b, c, nd = exact_vehicle_table_flex(s, rel, ddl, rmax, ro, rd, tt, dw, cap, n, node_limit)
        tabs.append(b)
        complete &= c
        nodes += nd
    g = {0: 0.0}
    for b in tabs:
        ng = dict(g)
        for M, cm in g.items():
            for S, cs in b.items():
                if S & M:
                    continue
                U = M | S
                v = cm + cs
                if v < ng.get(U, INF) - EPS:
                    ng[U] = v
        g = ng
    key = min((-bin(M).count("1"), round(c, 9)) for M, c in g.items())
    return -key[0], key[1], complete, nodes


def exact_by_permutations_flex(starts, rel, ddl, rmax, ro, rd, tt, dw, cap):
    """Unabhängige Kontrolle (n<=4, K<=2): alle Zuordnungen und Reihenfolgen; Zulässigkeit je Folge über Kapazität und STN."""
    n = len(rel)
    K = len(starts)
    best = None
    for assign in itertools.product(range(K + 1), repeat=n):
        total = 0.0
        ok = True
        served = 0
        for v in range(K):
            reqs = [r for r in range(n) if assign[r] == v]
            if not reqs:
                continue
            events = []
            for r in reqs:
                events.append((ro[r], r, False))
                events.append((rd[r], r, True))
            bestv = INF
            for perm in itertools.permutations(events):
                pos = {}
                bad = False
                load = 0
                for k, (s, r, isd) in enumerate(perm):
                    if isd and (r not in pos):
                        bad = True
                        break
                    pos[r] = k
                    load += -1 if isd else 1
                    if load > cap:
                        bad = True
                        break
                if bad:
                    continue
                if not stn_feasible(starts[v], list(perm), rel, ddl, rmax, tt, dw):
                    continue
                c = 0.0
                loc = starts[v]
                for s, r, isd in perm:
                    c += tt[loc][s] + dw
                    loc = s
                if c < bestv:
                    bestv = c
            if bestv == INF:
                ok = False
                break
            total += bestv
            served += len(reqs)
        if not ok:
            continue
        key = (-served, round(total, 9))
        if best is None or key < best:
            best = key
    return -best[0], best[1]
