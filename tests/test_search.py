"""Flottensuche, Qualitätsmaße, Kosten und Kipppunkt: von Hand gerechnete Fälle."""

import math

import pytest

import ruf_search as S
from ruf_network import World
from ruf_sim import INF, summarize


def _rows(served, totals=None, waits=None):
    return [{"K": k, "served": s, "total": (totals or [0] * len(served))[i], "wait": (waits or [0] * len(served))[i], "n_acc": 10, "n_req": 12, "busy_h": 1.0}
            for i, (k, s) in enumerate(zip(range(3, 3 + len(served)), served))]


def test_kstar_is_the_smallest_fleet_from_which_all_larger_fleets_pass():
    rows = _rows([0.95, 0.85, 0.92, 0.97, 0.99])          # K = 3..7: K = 3 besteht, K = 4 nicht, ab K = 5 alle
    K, row = S.kstar(rows)
    assert K == 5 and row["served"] == 0.92


def test_kstar_is_infinite_when_the_largest_scanned_fleet_fails():
    K, row = S.kstar(_rows([0.5, 0.7, 0.85]))
    assert K == INF and row is None


def test_kstar_with_a_total_time_limit_and_a_wait_limit():
    rows = _rows([0.95, 0.95, 0.95], totals=[40.0, 33.0, 29.0], waits=[9.0, 8.0, 7.0])
    assert S.kstar(rows, theta=35.0)[0] == 4
    assert S.kstar(rows, wait_max=7.5)[0] == 5
    assert S.kstar(rows, theta=20.0)[0] == INF


def test_nstar_line_uses_the_same_for_all_larger_rule():
    res = {2: {"reach": 0.5}, 3: {"reach": 0.95}, 4: {"reach": 0.8}, 5: {"reach": 0.95}, 6: {"reach": 0.99}}
    assert S.nstar_line(res, lambda v: v["reach"] >= 0.9) == 5


def test_line_cost_formula():
    assert S.line_cost(10, 100, 0.9) == pytest.approx(10 * 4.5 / 90.0)


def test_ruf_cost_bases():
    row = {"n_acc": 90, "n_req": 100, "busy_h": 27.0}
    assert S.ruf_cost(row, 8) == pytest.approx(8 * 4.5 / 90.0)
    assert S.ruf_cost(row, 8, "request") == pytest.approx(8 * 4.5 / 100.0)
    assert S.ruf_cost(row, 8, "busy") == pytest.approx(0.3)


def test_crossing_log_linear_by_hand_and_the_edge_cases():
    D = [1.0, 2.0, 4.0]
    assert S.crossing(D, [1.0, 2.0, 4.0], [2.0, 2.5, 3.0]) == pytest.approx(2.7067, rel=1e-3)   # Verhältnis 0,5 / 0,8 / 1,333
    assert S.crossing(D, [1.0, 1.0, 1.0], [2.0, 2.0, 2.0]) == INF                           # Rufbus überall billiger
    assert S.crossing(D, [3.0, 3.0, 3.0], [2.0, 2.0, 2.0]) == -INF                          # Linienbus schon am Anfang billiger
    assert S.crossing(D, [1.0, 1.0, 1.0], [INF, INF, INF]) == INF                           # Linie unmöglich: Rufbus gewinnt


def test_scan_stops_after_three_good_fleets_and_matches_a_direct_run():
    w = World(3, 10.0, 30, 50)
    rows = S.scan_ruf(w, 20.0, 4, 15.0, 1.5, "fcfs")
    ks = [r["K"] for r in rows]
    assert ks == list(range(ks[0], ks[0] + len(ks)))
    assert all(r["served"] >= 0.95 for r in rows[-3:])
    assert len(rows) == 3 or rows[-4]["served"] < 0.95      # sonst wäre früher abgebrochen worden
    direct = S.run_ruf(w, 20.0, rows[2]["K"], 4, 15.0, 1.5, "fcfs")
    assert summarize(direct)["served"] == rows[2]["served"]


def test_line_phases_are_reproducible_fractions():
    a = S.line_phases(3, 2, 4)
    assert a == S.line_phases(3, 2, 4) and all(0 <= x < 1 for x in a)
    assert a != S.line_phases(4, 2, 4)


def test_the_scan_is_deterministic():
    w = World(5, 10.0, 30, 50)
    r1 = S.scan_ruf(w, 15.0, 4, 15.0, 1.5)
    r2 = S.scan_ruf(w, 15.0, 4, 15.0, 1.5)
    assert [(r["K"], r["served"]) for r in r1] == [(r["K"], r["served"]) for r in r2]
    assert math.isfinite(S.kstar(r1)[0])


def test_kstar_is_the_first_fleet_when_every_scanned_fleet_passes():
    assert S.kstar(_rows([0.95, 0.96, 0.97]))[0] == 3


def test_line_phases_differ_between_designs():
    assert S.line_phases(3, 1, 4) != S.line_phases(3, 2, 4)


def test_line_wait_predicate_has_no_slack():
    p = S.line_pred("wait", 8.0)
    assert p({"reach": 0.95, "wait": 8.0, "rho": 0.1}) and not p({"reach": 0.95, "wait": 8.2, "rho": 0.1})
    assert not p({"reach": 0.85, "wait": 5.0, "rho": 0.1}) and not p({"reach": 0.95, "wait": 5.0, "rho": 1.2})
