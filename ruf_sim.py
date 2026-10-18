"""Rufbus (Dial-a-Ride): Einfügeheuristik, Online-Simulation (sofortige Zusage, Verbessern, Batch), Auswertung und unabhängiger Zulässigkeitsnachweis.

Kern aus der Vorab-Messreihe (oepnv-planung/messreihe_rufbus/core.py), geprüft gegen vollständige Aufzählung. Zufall (Mischen beim Verbessern)
kommt aus `ruf_rng.SplitMix64`, die Welt aus `ruf_network`.
"""
import math

from ruf_constants import DWELL, EPS, SLACK, T0_MEAS, T1_MEAS
from ruf_network import World  # noqa: F401  (hier wieder ausgeführt: `from ruf_sim import World`)
from ruf_rng import SplitMix64

INF = float("inf")


class Veh:
    __slots__ = ("id", "loc", "ta", "ev", "arr", "onboard", "prep", "start", "log")

    def __init__(self, i, loc):
        self.id = i
        self.loc = loc
        self.start = loc
        self.ta = 0.0
        self.ev = []        # (stop, req, isdrop)
        self.arr = []       # Ankunftszeiten der geplanten Ereignisse
        self.onboard = set()
        self.prep = None
        self.log = []       # ausgeführte Ereignisse: (arr, stop, req, isdrop)


class Sim:
    def __init__(self, tt, reqs, K, starts, cap, W, f, dwell=DWELL, slack=SLACK):
        self.tt, self.dw, self.cap, self.W, self.f = tt, dwell, cap, W, f
        n = len(reqs)
        self.n = n
        self.rt = [r[0] for r in reqs]
        self.ro = [r[1] for r in reqs]
        self.rd = [r[2] for r in reqs]
        self.ddl = [t + W for t in self.rt]
        self.rmax = [f * (tt[o][d] + dwell) + slack for _, o, d in reqs]
        self.pick = [None] * n
        self.drop = [None] * n
        self.veh_of = [-1] * n
        self.status = [0] * n      # 0 offen, 1 angenommen, 2 abgelehnt
        self.vs = [Veh(i, starts[i]) for i in range(K)]
        self.busy = []             # (von, bis) je ausgeführtem Ereignis
        self.cnt = {"reloc": 0, "swap": 0, "retry": 0, "reloc_try": 0, "swap_try": 0, "ins": 0}

    # ------------------------------------------------------------------ Zustand
    def advance(self, now):
        tt, dw = self.tt, self.dw
        for v in self.vs:
            while v.ev and v.arr[0] <= now + 1e-12:
                s, r, isd = v.ev.pop(0)
                a = v.arr.pop(0)
                self.busy.append((a - tt[v.loc][s], a + dw))
                v.log.append((a, s, r, isd))
                if isd:
                    v.onboard.discard(r)
                    self.drop[r] = a
                else:
                    v.onboard.add(r)
                    self.pick[r] = a
                v.loc = s
                v.ta = a + dw
                v.prep = None

    def recompute(self, v):
        tt, dw = self.tt, self.dw
        t, loc = v.ta, v.loc
        arr = []
        for s, _, _ in v.ev:
            t += tt[loc][s]
            arr.append(t)
            t += dw
            loc = s
        v.arr = arr
        v.prep = None

    def end_time(self, v, now):
        if v.ev:
            return v.arr[-1] + self.dw
        return v.ta if v.ta > now else now

    def first_index(self, v, now):
        return 1 if (v.ev and v.ta < now - EPS) else 0

    def _prep(self, v):
        ev, arr = v.ev, v.arr
        m = len(ev)
        slackP = [INF] * m
        slackR = [INF] * m
        kp = [-1] * m
        kd_of = [-1] * m
        posP = {}
        ddl, rmax, pick = self.ddl, self.rmax, self.pick
        for k in range(m):
            s, r, isd = ev[k]
            if not isd:
                slackP[k] = ddl[r] - arr[k]
                posP[r] = k
            else:
                if r in posP:
                    kk = posP[r]
                    kp[k] = kk
                    kd_of[kk] = k
                    ptime = arr[kk]
                else:
                    ptime = pick[r]
                slackR[k] = rmax[r] - (arr[k] - ptime)
        Lg = [0] * (m + 1)
        cur = len(v.onboard)
        Lg[0] = cur
        for k in range(m):
            cur += -1 if ev[k][2] else 1
            Lg[k + 1] = cur
        SP = [INF] * (m + 1)
        for k in range(m - 1, -1, -1):
            SP[k] = slackP[k] if slackP[k] < SP[k + 1] else SP[k + 1]
        v.prep = (slackP, slackR, kp, kd_of, Lg, SP)
        return v.prep

    # ------------------------------------------------------------------ Einfügen
    def best_ins(self, v, p, d, ddl_new, rmax_new, now, collect=None):
        """Beste zulässige Einfügeposition (i,j) von Abholung p und Ziel d in die Route von v.
        Rückgabe (Kosten, i, j) oder None. Kosten = Zunahme der Routenendzeit. collect: Liste aller zulässigen (Kosten,i,j)."""
        tt, dw, cap = self.tt, self.dw, self.cap
        ev, arr = v.ev, v.arr
        m = len(ev)
        if m == 0:
            t0 = v.ta if v.ta > now else now
            tP = t0 + tt[v.loc][p]
            if tP > ddl_new + EPS:
                return None
            c = tt[v.loc][p] + dw + tt[p][d] + dw
            if collect is not None:
                collect.append((c, 0, 0))
            return (c, 0, 0)
        pr = v.prep or self._prep(v)
        slackP, slackR, kp, kd_of, Lg, SP = pr
        old_end = arr[m - 1] + dw
        fi = self.first_index(v, now)
        best = None
        bc = INF
        ttp = tt[p]
        ttd = tt[d]
        for i in range(fi, m + 1):
            if i == 0:
                pl, pd = v.loc, v.ta
            else:
                pl, pd = ev[i - 1][0], arr[i - 1] + dw
            tP = pd + tt[pl][p]
            if tP > ddl_new + EPS:
                continue
            if Lg[i] + 1 > cap:
                continue
            depP = tP + dw
            if i == m:
                tD = depP + ttp[d]
                if tD - tP > rmax_new + EPS:
                    continue
                c = tD + dw - old_end
                if collect is not None:
                    collect.append((c, i, i))
                if c < bc - EPS:
                    bc, best = c, (c, i, i)
                continue
            s_i = ev[i][0]
            # SRs[j]: min slackR über Zielereignisse kd>=j, deren Abholung vor i liegt (oder schon erfolgt ist)
            SRs = [INF] * (m + 1)
            x = INF
            for k in range(m - 1, i - 1, -1):
                if ev[k][2] and kp[k] < i:
                    if slackR[k] < x:
                        x = slackR[k]
                SRs[k] = x
            # j == i: Ziel direkt nach der Abholung
            tD = depP + ttp[d]
            if tD - tP <= rmax_new + EPS:
                a = tD + dw + ttd[s_i]
                dj = a - arr[i]
                if dj <= SP[i] + EPS and dj <= SRs[i] + EPS:
                    if collect is not None:
                        collect.append((dj, i, i))
                    if dj < bc - EPS:
                        bc, best = dj, (dj, i, i)
            di = depP + ttp[s_i] - arr[i]
            rp = INF
            rr = INF
            act = []
            for j in range(i + 1, m + 1):
                k = j - 1
                if slackP[k] < rp:
                    rp = slackP[k]
                if ev[k][2]:
                    if kp[k] < i and slackR[k] < rr:
                        rr = slackR[k]
                else:
                    kd = kd_of[k]
                    act.append((kd, slackR[kd]))
                if di > rp + EPS or di > rr + EPS:
                    break
                if Lg[j] + 1 > cap:
                    break
                tD = arr[k] + dw + di + tt[ev[k][0]][d]
                if tD - tP > rmax_new + EPS:
                    break
                if j == m:
                    c = tD + dw - old_end
                    if collect is not None:
                        collect.append((c, i, j))
                    if c < bc - EPS:
                        bc, best = c, (c, i, j)
                else:
                    a = tD + dw + ttd[ev[j][0]]
                    dj = a - arr[j]
                    if dj <= SP[j] + EPS and dj <= SRs[j] + EPS:
                        ok = True
                        for kd, sr in act:
                            if kd >= j and dj - di > sr + EPS:
                                ok = False
                                break
                        if ok:
                            if collect is not None:
                                collect.append((dj, i, j))
                            if dj < bc - EPS:
                                bc, best = dj, (dj, i, j)
        return best

    def commit(self, v, r, i, j, now):
        if not v.ev:
            if v.ta < now:
                v.ta = now
        p, d = self.ro[r], self.rd[r]
        new = v.ev[:i] + [(p, r, False)] + v.ev[i:j] + [(d, r, True)] + v.ev[j:]
        v.ev = new
        self.recompute(v)
        self.veh_of[r] = v.id
        self.status[r] = 1
        self.cnt["ins"] += 1

    def remove(self, v, r):
        v.ev = [e for e in v.ev if e[1] != r]
        self.recompute(v)

    def cand(self, v, r, now):
        return self.best_ins(v, self.ro[r], self.rd[r], self.ddl[r], self.rmax[r], now)

    def best_over(self, r, now, vs=None):
        best = None
        for v in (vs if vs is not None else self.vs):
            c = self.cand(v, r, now)
            if c is not None and (best is None or c[0] < best[0][0] - EPS):
                best = (c, v)
        return best

    # ------------------------------------------------------------------ FCFS
    def run_fcfs(self):
        for r in range(self.n):
            now = self.rt[r]
            self.advance(now)
            b = self.best_over(r, now)
            if b is None:
                self.status[r] = 2
            else:
                (c, i, j), v = b
                self.commit(v, r, i, j, now)
        self.advance(INF)
        return self

    # ------------------------------------------------------------------ Batch
    def movable(self, now):
        out = []
        for v in self.vs:
            fi = self.first_index(v, now)
            for k in range(fi, len(v.ev)):
                s, r, isd = v.ev[k]
                if not isd:
                    out.append((r, v))
        return out

    def plan_batch(self, pend, now, rng, improve=True, max_pass=3, swap_trials=40):
        un = list(pend)
        cache = {}
        rejected = []
        for r in un:
            cache[r] = {v.id: self.cand(v, r, now) for v in self.vs}
        while un:
            best_r, best_key = None, None
            for r in list(un):
                feas = sorted((c[0], vid) for vid, c in cache[r].items() if c is not None)
                if not feas:
                    un.remove(r)
                    rejected.append(r)
                    continue
                regret = (feas[1][0] - feas[0][0]) if len(feas) > 1 else 1e6
                key = (-regret, feas[0][0], r)
                if best_key is None or key < best_key:
                    best_key, best_r = key, r
            if best_r is None:
                break
            r = best_r
            c, vid = min((c[0], vid) for vid, c in cache[r].items() if c is not None)
            v = self.vs[vid]
            cc = cache[r][vid]
            self.commit(v, r, cc[1], cc[2], now)
            un.remove(r)
            for r2 in un:
                cache[r2][vid] = self.cand(v, r2, now)
        if improve:
            for _ in range(max_pass):
                changed = False
                # Umlegen
                mv = self.movable(now)
                rng.shuffle(mv)
                for r, v in mv:
                    if self.pick[r] is not None or v.id != self.veh_of[r]:
                        continue
                    if not any(e[1] == r for e in v.ev):
                        continue
                    # nur beweglich, wenn die Abholung nicht gefroren ist
                    idx = next(q for q, e in enumerate(v.ev) if e[1] == r and not e[2])
                    if idx < self.first_index(v, now):
                        continue
                    self.cnt["reloc_try"] += 1
                    saved = list(v.ev)
                    before = self.end_time(v, now)
                    self.remove(v, r)
                    after = self.end_time(v, now)
                    saving = before - after
                    b = self.best_over(r, now)
                    if b is not None and b[0][0] < saving - 1e-7 - 0.0:
                        (c, i, j), v2 = b
                        self.commit(v2, r, i, j, now)
                        self.cnt["reloc"] += 1
                        changed = True
                    else:
                        v.ev = saved
                        self.recompute(v)
                # Austauschen (Stichprobe von Paaren)
                mv = self.movable(now)
                pairs = [(a, b) for ai, a in enumerate(mv) for b in mv[ai + 1:] if a[1].id != b[1].id]
                rng.shuffle(pairs)
                for (ra, va), (rb, vb) in pairs[:swap_trials]:
                    if self.veh_of[ra] != va.id or self.veh_of[rb] != vb.id:
                        continue
                    if self.pick[ra] is not None or self.pick[rb] is not None:
                        continue
                    ia = next((q for q, e in enumerate(va.ev) if e[1] == ra and not e[2]), None)
                    ib = next((q for q, e in enumerate(vb.ev) if e[1] == rb and not e[2]), None)
                    if ia is None or ib is None:
                        continue
                    if ia < self.first_index(va, now) or ib < self.first_index(vb, now):
                        continue
                    self.cnt["swap_try"] += 1
                    sa, sb = list(va.ev), list(vb.ev)
                    before = self.end_time(va, now) + self.end_time(vb, now)
                    self.remove(va, ra)
                    self.remove(vb, rb)
                    ca = self.cand(vb, ra, now)
                    ok = False
                    if ca is not None:
                        self.commit(vb, ra, ca[1], ca[2], now)
                        cb = self.cand(va, rb, now)
                        if cb is not None:
                            self.commit(va, rb, cb[1], cb[2], now)
                            after = self.end_time(va, now) + self.end_time(vb, now)
                            if after < before - 1e-7:
                                ok = True
                    if ok:
                        self.cnt["swap"] += 1
                        changed = True
                    else:
                        va.ev, vb.ev = sa, sb
                        self.recompute(va)
                        self.recompute(vb)
                        self.veh_of[ra], self.veh_of[rb] = va.id, vb.id
                # Wiederholungsversuch für abgelehnte
                for r in list(rejected):
                    b = self.best_over(r, now)
                    if b is not None:
                        (c, i, j), v = b
                        self.commit(v, r, i, j, now)
                        rejected.remove(r)
                        self.cnt["retry"] += 1
                        changed = True
                if not changed:
                    break
        for r in rejected:
            self.status[r] = 2

    def run_ols(self, rng, max_pass=2, swap_trials=20):
        """Online mit sofortiger Zusage (wie FCFS) plus anschließender Verbesserung (Umlegen/Austauschen) aller noch nicht abgeholten Anfragen."""
        for r in range(self.n):
            now = self.rt[r]
            self.advance(now)
            self.plan_batch([r], now, rng, improve=True, max_pass=max_pass, swap_trials=swap_trials)
        self.advance(INF)
        return self

    def run_batch(self, B, rng, improve=True):
        pend = []
        t_next = B
        r = 0
        n = self.n
        while r < n or pend:
            # sammle alle Anfragen bis t_next
            while r < n and self.rt[r] <= t_next:
                pend.append(r)
                r += 1
            self.advance(t_next)
            if pend:
                self.plan_batch(pend, t_next, rng, improve=improve)
                pend = []
            t_next += B
            if r >= n:
                break
        self.advance(INF)
        return self


# ---------------------------------------------------------------------- Auswertung
def summarize(sim, t0=T0_MEAS, t1=T1_MEAS):
    idx = [r for r in range(sim.n) if t0 <= sim.rt[r] < t1]
    acc = [r for r in idx if sim.status[r] == 1]
    out = {"n_req": len(idx), "n_acc": len(acc)}
    out["served"] = len(acc) / len(idx) if idx else 1.0
    if acc:
        w = [sim.pick[r] - sim.rt[r] for r in acc]
        rd = [sim.drop[r] - sim.pick[r] for r in acc]
        direct = [sim.tt[sim.ro[r]][sim.rd[r]] + sim.dw for r in acc]
        out["wait"] = sum(w) / len(w)
        out["ride"] = sum(rd) / len(rd)
        out["total"] = out["wait"] + out["ride"]
        out["detour"] = sum(rd) / sum(direct)
        ws = sorted(w)
        out["wait_p90"] = ws[min(len(ws) - 1, int(0.9 * len(ws)))]
    else:
        out.update({"wait": 0.0, "ride": 0.0, "total": 0.0, "detour": 1.0, "wait_p90": 0.0})
    bt = 0.0
    for a, b in sim.busy:
        lo, hi = max(a, t0), min(b, t1)
        if hi > lo:
            bt += hi - lo
    out["busy_h"] = bt / 60.0
    # Bündelung
    per_v = {}
    for r in acc:
        per_v.setdefault(sim.veh_of[r], []).append((sim.pick[r], sim.drop[r]))
    shared = 0
    cor = 0.0
    paxmin = 0.0
    for lst in per_v.values():
        for a, (p1, d1) in enumerate(lst):
            ov = 0.0
            sh = False
            for b, (p2, d2) in enumerate(lst):
                if a == b:
                    continue
                o = min(d1, d2) - max(p1, p2)
                if o > 1e-9:
                    ov += o
                    sh = True
            shared += 1 if sh else 0
            cor += ov / (d1 - p1) if d1 > p1 else 0.0
            paxmin += d1 - p1
    out["shared"] = shared / len(acc) if acc else 0.0
    out["corider"] = cor / len(acc) if acc else 0.0
    out["occ"] = (paxmin / 60.0) / out["busy_h"] if out["busy_h"] > 0 else 0.0
    return out


def validate(sim, W, f, cap, slack=SLACK):
    """Unabhängiger Nachweis aus den Ausführungsprotokollen. Gibt Liste der Verstöße zurück (leer = zulässig)."""
    errs = []
    tt, dw = sim.tt, sim.dw
    seen_p, seen_d = {}, {}
    busy_chk = 0.0
    for v in sim.vs:
        log = sorted(v.log)
        loc, tprev = v.start, None
        load = 0
        for a, s, r, isd in log:
            if tprev is None:
                if a < tt[loc][s] - 1e-6:
                    errs.append(("start", v.id, r))
            else:
                if a < tprev + tt[loc][s] - 1e-6:
                    errs.append(("fahrzeit", v.id, r, a, tprev, tt[loc][s]))
            busy_chk += tt[loc][s] + dw
            tprev = a + dw
            loc = s
            if isd:
                if s != sim.rd[r]:
                    errs.append(("zielort", r))
                seen_d[r] = (a, v.id)
                load -= 1
            else:
                if s != sim.ro[r]:
                    errs.append(("startort", r))
                seen_p[r] = (a, v.id)
                load += 1
            if load > cap:
                errs.append(("kapazitaet", v.id, r))
            if load < 0:
                errs.append(("negativ", v.id, r))
        if load != 0:
            errs.append(("restlast", v.id))
    for r in range(sim.n):
        if sim.status[r] == 1:
            if r not in seen_p or r not in seen_d:
                errs.append(("unvollstaendig", r))
                continue
            pa, pv = seen_p[r]
            da, dv = seen_d[r]
            if pv != dv:
                errs.append(("fahrzeugwechsel", r))
            if pa < sim.rt[r] - 1e-9:
                errs.append(("zu_frueh", r))
            if pa - sim.rt[r] > W + 1e-6:
                errs.append(("wartezeit", r, pa - sim.rt[r]))
            if da <= pa:
                errs.append(("reihenfolge", r))
            direct = tt[sim.ro[r]][sim.rd[r]] + dw
            if da - pa > f * direct + slack + 1e-6:
                errs.append(("umweg", r, da - pa))
        else:
            if r in seen_p or r in seen_d:
                errs.append(("abgelehnt_aber_gefahren", r))
    tot_busy = sum(b - a for a, b in sim.busy)
    if abs(tot_busy - busy_chk) > 1e-6:
        errs.append(("busy", tot_busy, busy_chk))
    return errs


def run_one(world, lam, K, cap, W, f, proc="fcfs", B=5.0, search_seed=0, improve=True):
    reqs = world.requests(lam)
    sim = Sim(world.tt, reqs, K, world.starts, cap, W, f)
    if proc == "fcfs":
        sim.run_fcfs()
    elif proc == "ols":
        sim.run_ols(SplitMix64(search_seed))
    else:
        sim.run_batch(B, SplitMix64(search_seed), improve=improve)
    return sim
