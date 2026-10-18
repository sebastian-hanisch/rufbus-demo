"""Einfügeheuristik und Simulation an einer Mini-Instanz, von Hand gerechnet (DEMO-PLAYBOOK §1b).

Drei Haltepunkte auf einer Geraden (6 min zwischen Nachbarn, 12 min zwischen den Enden), Halt 0,5 min, ein Fahrzeug startet an Haltepunkt 0."""

import pytest

from ruf_sim import INF, Sim, summarize, validate


def _sim(tt3, reqs, K=1, cap=4, W=15.0, f=1.5):
    return Sim(tt3, reqs, K, [0] * 8, cap, W, f)


def test_first_request_cost_is_pickup_plus_ride_plus_two_stops(tt3):
    sim = _sim(tt3, [(0.0, 0, 2)])
    sim.run_fcfs()
    assert sim.status == [1]
    assert sim.pick[0] == 0.0
    assert sim.drop[0] == 12.5                      # 0,5 min Halt, dann 12 min Fahrt
    assert sum(b - a for a, b in sim.busy) == pytest.approx(13.0)   # Aufnahme 0,5 + Fahrt 12 + Absetzen 0,5
    assert validate(sim, 15.0, 1.5, 4) == []


def test_second_request_waits_for_the_first_ride_and_misses_the_deadline(tt3):
    # B (1 -> 2) kommt bei t = 1; das Fahrzeug ist zum Haltepunkt 2 unterwegs (erster Halt gesperrt), Abholung erst nach 12,5 + 0,5 + 6 = 19 min
    sim = _sim(tt3, [(0.0, 0, 2), (1.0, 1, 2)], W=15.0)
    sim.run_fcfs()
    assert sim.status == [1, 2]                      # 19 > 1 + 15: abgelehnt


def test_second_request_is_accepted_with_a_longer_wait_budget_and_costs_13(tt3):
    sim = _sim(tt3, [(0.0, 0, 2), (1.0, 1, 2)], W=25.0)
    sim.run_fcfs()
    assert sim.status == [1, 1]
    assert sim.pick[1] == 19.0 and sim.drop[1] == 25.5      # 12,5 + 0,5 Halt + 6 Fahrt = 19; dann 0,5 + 6
    assert sum(b - a for a, b in sim.busy) == pytest.approx(13.0 + 13.0)
    assert validate(sim, 25.0, 1.5, 4) == []


def test_capacity_one_blocks_sharing_and_capacity_two_allows_it(tt3):
    reqs = [(0.0, 0, 2), (0.0, 0, 2)]
    s1 = _sim(tt3, reqs, cap=1)
    s1.run_fcfs()
    assert s1.status == [1, 2]
    s2 = _sim(tt3, reqs, cap=2)
    s2.run_fcfs()
    assert s2.status == [1, 1]
    assert s2.pick[0] == 0.0 and s2.pick[1] == 0.5       # zweite Abholung nach dem Halt der ersten
    assert validate(s2, 15.0, 1.5, 2) == []


def test_detour_limit_allows_a_stop_for_a_second_passenger_within_the_slack(tt3):
    # A: 0 -> 2, direkt 12,5 min; mit f = 1,0 darf A höchstens 12,5 + 2 = 14,5 min unterwegs sein.
    # B: 1 -> 2. Hält das Fahrzeug für B bei Haltepunkt 1, fährt A 0,5 + 6 + 0,5 + 6 = 13 min (oder 13,5, wenn B zuerst abgesetzt wird) <= 14,5: zulässig, beide werden bedient.
    sim = _sim(tt3, [(0.0, 0, 2), (0.0, 1, 2)], cap=4, f=1.0)
    sim.run_fcfs()
    assert sim.status == [1, 1]
    assert validate(sim, 15.0, 1.0, 4) == []
    ride = sim.drop[0] - sim.pick[0]
    assert 12.5 < ride <= 14.5          # länger als direkt (Halt bei 1), aber innerhalb der Grenze; je nach Reihenfolge der beiden Absetzhalte 13,0 oder 13,5


def test_summarize_counts_only_requests_in_the_measurement_window(tt3):
    reqs = [(10.0, 0, 2), (60.0, 0, 2), (400.0, 0, 2)]
    sim = _sim(tt3, reqs)
    sim.run_fcfs()
    s = summarize(sim)
    assert (s["n_req"], s["n_acc"], s["served"]) == (1, 1, 1.0)      # nur t = 60 liegt in [45, 315)


def test_inf_is_a_float_infinity():
    assert INF == float("inf")


def test_limits_follow_the_wait_budget_and_the_detour_formula(tt3):
    sim = _sim(tt3, [(0.0, 0, 2)], W=15.0, f=1.5)
    assert sim.ddl[0] == 15.0
    assert sim.rmax[0] == pytest.approx(1.5 * (12.0 + 0.5) + 2.0)         # 20,75: Faktor mal (Direktfahrt plus Halt) plus 2 min


def test_summarize_means_by_hand(tt3):
    sim = _sim(tt3, [(50.0, 0, 2), (51.0, 1, 2)], W=25.0)
    sim.run_fcfs()
    s = summarize(sim)
    assert s["n_req"] == 2 and s["served"] == 1.0
    assert s["wait"] == pytest.approx(9.0)        # 0 und 18 min: Mittel 9 (nicht das Maximum 18)
    assert s["ride"] == pytest.approx(9.5)        # 12,5 und 6,5 min
    assert s["total"] == pytest.approx(18.5)


def test_the_improvement_step_never_lengthens_the_routes_when_nothing_is_rejected():
    """Verbessern (Umlegen, Austauschen) nimmt nur Züge an, die die Summe der Routenenden verkürzen; Einfügen davor ist in beiden Läufen gleich."""
    from ruf_network import World
    from ruf_rng import SplitMix64
    strict = compared = 0
    for s in range(40):
        w = World(1 + s % 20, 10.0, 30, 50)
        pool = [r for r in w.requests(120.0) if 60.0 <= r[0] < 80.0][:10]
        reqs = [(60.0, o, d) for _, o, d in pool]
        ends = []
        for improve in (False, True):
            sim = Sim(w.tt, reqs, 6, w.starts, 4, 15.0, 1.5)
            sim.advance(60.0)
            sim.plan_batch(list(range(len(reqs))), 60.0, SplitMix64(s), improve=improve)
            if any(x == 2 for x in sim.status):
                break
            ends.append(sum(sim.end_time(v, 60.0) for v in sim.vs))
        else:
            compared += 1
            assert ends[1] <= ends[0] + 1e-7
            strict += ends[1] < ends[0] - 1e-7
    assert compared >= 10 and strict >= 1
