"""Linienbus: Zeiten einer Linie von Hand, Winkelreihenfolge gegen atan2, Wegetabelle gegen networkx (unabhängiger Rechenweg)."""

import math
from types import SimpleNamespace

import networkx as nx
import numpy as np
import pytest

import ruf_constants as C
import ruf_line as LN
from ruf_network import World


def _world3(tt3):
    return SimpleNamespace(tt=tt3)


def test_line_cycle_and_stop_times_by_hand(tt3):
    ln = LN.Line(_world3(tt3), [0, 1, 2])
    assert ln.seg == [6.5, 6.5]                      # 6 min Fahrt + 0,5 min Halt
    assert ln.tauf == [0.0, 6.5, 13.0]
    assert ln.taub == [28.0, 21.5, 15.0]             # Rückrichtung beginnt 13 + 2 min Wende nach der Abfahrt vorn
    assert ln.C == 30.0                              # Umlaufzeit = Rückkehr + 2 min Wende


def test_allocation_gives_extra_vehicles_to_the_longest_cycle_per_vehicle():
    assert LN.alloc_vehicles([30.0, 20.0], 3) == [2, 1]
    assert LN.alloc_vehicles([30.0, 20.0], 5) == [3, 2]
    assert LN.alloc_vehicles([30.0, 20.0], 1) is None


def test_split_matches_array_split_sizes():
    for n in range(1, 40):
        for parts in (2, 4, 6, 8):
            ref = [len(c) for c in np.array_split(np.arange(n), parts)]
            assert [len(c) for c in LN._split(list(range(n)), parts)] == ref


@pytest.mark.parametrize("seed", range(6))
def test_angle_order_equals_atan2_order(seed):
    w = World(seed + 1, 10.0, 24, 50)
    hub = w.hub
    others = [i for i in range(w.n) if i != hub]
    gx, gy = int(w.grid[hub][0]), int(w.grid[hub][1])
    key = {i: math.atan2(int(w.grid[i][1]) - gy, int(w.grid[i][0]) - gx) for i in others}
    assert LN._angle_order(w, hub, others) == sorted(others, key=lambda i: (key[i], i))      # Gleichstände (gleiche Richtung) nach Index


def test_designs_cover_every_stop_or_the_demanded_ones():
    w = World(4, 10.0, 30, 50)
    assert sorted(LN.design_lines(w, "R")[0]) == list(range(30))
    star = LN.design_lines(w, "S3")
    assert len(star) == 3 and all(w.hub in ln for ln in star)
    assert sorted({s for ln in star for s in ln}) == list(range(30))
    part = LN.design_lines(w, "P1")[0]
    acc, walk = LN.design_access(w, "P1")
    assert set(part) <= set(range(30)) and (acc >= 0).sum() >= len(part)
    assert all(acc[s] == s for s in part)


def _expected_times_networkx(lines, Nl, origin):
    """Erwartete Zeit origin -> alle Haltepunkte auf dem expandierten Graphen: Einstieg h/2 (+1 min Umstieg, wenn nicht am Ursprung), Fahrt je Segment."""
    h = [lines[l].C / Nl[l] for l in range(len(lines))]
    g = nx.DiGraph()
    for l, ln in enumerate(lines):
        for p, s in enumerate(ln.stops):
            node = ("l", l, p)
            g.add_edge(("s", s), node, weight=h[l] / 2.0 + (C.TRANSFER if s != origin else 0.0))
            g.add_edge(node, ("s", s), weight=0.0)
            if p + 1 < ln.P:
                g.add_edge(node, ("l", l, p + 1), weight=ln.seg[p])
                g.add_edge(("l", l, p + 1), node, weight=ln.seg[p])
    return nx.single_source_dijkstra_path_length(g, ("s", origin), weight="weight")


@pytest.mark.parametrize("design, N", [("R", 10), ("S2", 9), ("S3", 12)])
def test_route_table_expected_times_equal_networkx(design, N):
    w = World(3, 10.0, 20, 50)
    lines = [LN.Line(w, s) for s in LN.design_lines(w, design)]
    Nl = LN.alloc_vehicles([ln.C for ln in lines], N)
    LEG, EXP, h = LN.route_table(w, lines, Nl)
    for o in (0, 5, 11, 19):
        ref = _expected_times_networkx(lines, Nl, o)
        for d in range(w.n):
            if d == o:
                continue
            assert EXP[o, d] == pytest.approx(ref[("s", d)], abs=1e-9)


def test_evaluate_waiting_time_is_about_half_a_headway():
    """Fahrgäste, die gleichverteilt zu einer Linie kommen, warten im Mittel etwa den halben Takt, nie länger als einen Takt."""
    w = World(2, 10.0, 12, 50)
    ln = LN.Line(w, LN.design_lines(w, "R")[0])
    Nl = [4]
    LEG, EXP, h = LN.route_table(w, [ln], Nl)
    res = LN.evaluate(w, [ln], Nl, LEG, h, w.requests(120.0), [0.3 * h[0]], C.T0_MEAS, C.T1_MEAS)
    assert res["ok"].all()
    assert 0.35 * h[0] < res["wait"].mean() < 0.65 * h[0]
    assert res["wait"].max() <= h[0] + 1e-9


@pytest.mark.parametrize("design, radius", [("P1", 1.0), ("P2", 1.5)])
def test_partial_design_covers_the_demanded_share(design, radius):
    """Mindestens 97 % des Nachfragegewichts haben beide Enden im Einzugsbereich einer Linienhaltestelle."""
    w = World(6, 10.0, 30, 50)
    line_stops, acc, walk = LN.partial_design(w, radius)
    covered = [i for i in range(w.n) if acc[i] >= 0]
    share = sum(int(w.demand[i][j]) for i in covered for j in covered) / int(w.demand.sum())
    assert share >= 0.97
    assert all(w.dist[i, acc[i]] <= radius + 1e-9 for i in covered)
