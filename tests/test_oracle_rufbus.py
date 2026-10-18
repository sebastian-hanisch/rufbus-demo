"""Orakel-Tests (ORACLE-PLAYBOOK §2): die schnelle Einfügeheuristik gegen vollständige Aufzählung, ganze Läufe gegen einen Prüfer aus den
Ausführungsprotokollen, die exakte Aufzählung gegen Permutationen. Jeder Rechenweg ist unabhängig vom geprüften Code geschrieben
(`ruf_exact.sim_route` bewertet jede Folge von Grund auf)."""

import itertools

import pytest

import ruf_constants as C
import ruf_search as S
from ruf_exact import brute_insert, exact_by_permutations_flex, exact_solve_flex, sim_route
from ruf_network import World
from ruf_rng import SplitMix64
from ruf_sim import EPS, Sim, summarize, validate


def _random_state(s):
    rng = SplitMix64(1000 + s)
    n_stops = 6 + rng.below(5)
    L = (3.0, 4.0, 6.0)[rng.below(3)]
    w = World(1 + s % 40, L, n_stops, 50)
    K = 1 + rng.below(3)
    cap = (2, 3, 4)[rng.below(3)]
    W = (8.0, 12.0, 15.0)[rng.below(3)]
    f = (1.3, 1.5, 2.0)[rng.below(3)]
    m0 = 1 + rng.below(7)
    ts = sorted(rng.below(12000) / 1000.0 for _ in range(m0 + 1))
    reqs = []
    for t in ts:
        o = rng.below(n_stops)
        d = rng.below(n_stops - 1)
        d = d + 1 if d >= o else d
        reqs.append((t, o, d))
    sim = Sim(w.tt, reqs, K, w.starts, cap, W, f)
    for r in range(m0):
        now = sim.rt[r]
        sim.advance(now)
        b = sim.best_over(r, now)
        if b is None:
            sim.status[r] = 2
        else:
            (c, i, j), v = b
            sim.commit(v, r, i, j, now)
    sim.advance(sim.rt[m0])
    return sim, m0


@pytest.mark.parametrize("block", range(6))
def test_insertion_matches_full_enumeration(block):
    """Je Zustand und Fahrzeug: Menge der zulässigen Einfügepositionen und ihre Kosten stimmen mit der Aufzählung überein."""
    checked = nontrivial = 0
    for s in range(block * 25, block * 25 + 25):
        sim, rn = _random_state(s)
        tnow = sim.rt[rn]
        for v in sim.vs:
            t0 = v.ta if v.ev else max(v.ta, tnow)
            fi = sim.first_index(v, tnow)
            onboard_pick = {r: sim.pick[r] for r in v.onboard}
            if sim_route(v.loc, t0, list(v.ev), sim.rt, sim.ddl, sim.rmax, sim.tt, sim.dw, sim.cap, onboard_pick) is None:
                continue
            brute = brute_insert(v.loc, t0, list(v.ev), rn, sim.rt, sim.ddl, sim.rmax, sim.tt, sim.dw, sim.cap, onboard_pick, fi, sim.ro, sim.rd)
            coll = []
            fast = sim.best_ins(v, sim.ro[rn], sim.rd[rn], sim.ddl[rn], sim.rmax[rn], tnow, collect=coll)
            checked += 1
            if not v.ev:
                assert bool(brute) == bool(coll)
                if brute:
                    assert brute[(0, 0)] == pytest.approx(coll[0][0], abs=1e-7)
                continue
            fast_set = {(i, j): c for c, i, j in coll}
            assert len(fast_set) == len(coll)
            assert set(fast_set) == set(brute)
            for k, c in brute.items():
                assert fast_set[k] == pytest.approx(c, abs=1e-7)
            if brute:
                assert fast is not None and fast[0] == pytest.approx(min(brute.values()), abs=1e-7)
                nontrivial += fast[2] > fast[1]
            else:
                assert fast is None
    assert checked > 10


@pytest.mark.parametrize("proc", ["fcfs", "ols", "batch"])
def test_whole_runs_are_feasible_by_the_independent_checker(proc):
    """Der Prüfer liest nur die Ausführungsprotokolle (Fahrzeit, Kapazität, Wartezeit, Umweg, Reihenfolge, Zielort, Kostenbuchführung)."""
    for s in range(14):
        rng = SplitMix64(5000 + s)
        w = World(1 + s % 30, (6.0, 10.0, 16.0)[rng.below(3)], 30, 50)
        lam = (5, 15, 30, 60)[rng.below(4)]
        K = (1, 2, 4, 8, 12)[rng.below(5)]
        cap = (4, 8)[rng.below(2)]
        W = (10.0, 15.0, 25.0)[rng.below(3)]
        f = (1.5, 2.0)[rng.below(2)]
        sim = S.run_ruf(w, float(lam), K, cap, W, f, proc=proc, B=(2.0, 5.0)[rng.below(2)], search_seed=s)
        assert validate(sim, W, f, cap) == [], (proc, s)
        assert summarize(sim)["n_req"] >= 0


def test_exact_enumeration_matches_the_permutation_oracle_on_tiny_instances():
    """Exakte Aufzählung (mit freiem Abwarten) gegen vollständige Permutationsaufzählung für n <= 4 Anfragen, K <= 2 Fahrzeuge."""
    for s in range(120):
        rng = SplitMix64(900 + s)
        w = World(1 + s % 20, 6.0, 8, 50)
        n = 3 + rng.below(2)
        K = 2
        cap = (2, 4)[rng.below(2)]
        W = (10.0, 15.0, 30.0)[rng.below(3)]
        f = (1.5, 2.0)[rng.below(2)]
        reqs = []
        for _ in range(n):
            o = rng.below(8)
            d = rng.below(7)
            reqs.append((rng.below(8000) / 1000.0, o, d + 1 if d >= o else d))
        reqs.sort()
        starts = w.starts[:K]
        rel = [r[0] for r in reqs]
        ddl = [t + W for t in rel]
        rmax = [f * (w.tt[o][d] + C.DWELL) + C.SLACK for _, o, d in reqs]
        ro, rd = [r[1] for r in reqs], [r[2] for r in reqs]
        served, cost, complete, _ = exact_solve_flex(starts, rel, ddl, rmax, ro, rd, w.tt, C.DWELL, cap)
        ps, pc = exact_by_permutations_flex(starts, rel, ddl, rmax, ro, rd, w.tt, C.DWELL, cap)
        assert complete
        assert served == ps and cost == pytest.approx(pc, abs=1e-6), s


def test_no_heuristic_beats_the_exact_value_on_small_lots():
    for s in range(20):
        rng = SplitMix64(300 + s)
        w = World(1 + s % 20, 10.0, 30, 50)
        pool = [r for r in w.requests(120.0) if 60.0 <= r[0] < 160.0]
        rng.shuffle(pool)
        reqs = [(0.0, o, d) for _, o, d in sorted(pool[:6])]
        K = 1 + rng.below(2)
        starts = w.starts[:K]
        rel = [0.0] * len(reqs)
        W, f, cap = 15.0, 1.5, 4
        ddl = [W] * len(reqs)
        rmax = [f * (w.tt[o][d] + C.DWELL) + C.SLACK for _, o, d in reqs]
        ro, rd = [r[1] for r in reqs], [r[2] for r in reqs]
        served, cost, complete, _ = exact_solve_flex(starts, rel, ddl, rmax, ro, rd, w.tt, C.DWELL, cap)
        sim = Sim(w.tt, reqs, K, starts, cap, W, f)
        sim.run_fcfs()
        assert complete and sum(1 for x in sim.status if x == 1) <= served
