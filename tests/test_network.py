"""Szenario: ganzzahliger Generator, eingefrorene Referenzwerte (müssen auf jeder Plattform und mit jeder numpy-Version gleich sein)."""

import pytest

from ruf_network import World, generate_network


def test_frozen_network_for_seed_7():
    grid, demand, hubs = generate_network(6, 7, 50)
    assert grid.tolist() == [[42, 92], [40, 78], [80, 11], [87, 12], [25, 40], [95, 13]]
    assert demand.tolist() == [[0, 4, 20, 16, 4, 32], [4, 0, 2, 32, 1, 4], [20, 2, 0, 40, 4, 6], [16, 32, 40, 0, 4, 24], [4, 1, 4, 4, 0, 7], [32, 4, 6, 24, 7, 0]]
    assert hubs == [3, 0]


def test_demand_is_symmetric_with_zero_diagonal_and_positive_entries():
    _, demand, _ = generate_network(20, 11, 50)
    assert (demand == demand.T).all()
    assert all(demand[i, i] == 0 for i in range(20))
    assert min(int(demand[i, j]) for i in range(20) for j in range(20) if i != j) >= 1


@pytest.mark.parametrize("seed, first_stops, hub, n_base, n40, n6, first_request", [
    (1, [(63, 89), (6, 47), (10, 7), (61, 29)], 8, 741, 253, 41, (0.2833, 28, 25)),
    (2, [(65, 40), (89, 83), (22, 77), (54, 73)], 4, 726, 256, 43, (1.05, 10, 13)),
    (3, [(14, 8), (32, 12), (78, 69), (69, 89)], 27, 706, 219, 36, (0.4167, 26, 16)),
])
def test_frozen_world(seed, first_stops, hub, n_base, n40, n6, first_request):
    w = World(seed, 10.0, 30, 50)
    assert [tuple(int(v) for v in g) for g in w.grid[:4]] == first_stops
    assert w.hub == hub
    assert len(w._t) == n_base and len(w.requests(40)) == n40 and len(w.requests(6)) == n6
    t, o, d = w.requests(120)[0]
    assert (round(t, 4), o, d) == first_request


def test_thinning_is_monotone_a_lower_rate_is_a_subset():
    w = World(5, 10.0, 30, 50)
    a, b, c = set(w.requests(10)), set(w.requests(40)), set(w.requests(120))
    assert a <= b <= c


def test_travel_times_follow_distance_and_speed():
    w = World(1, 10.0, 30, 50)
    (x0, y0), (x1, y1) = w.grid[0], w.grid[1]
    km = ((int(x0) - int(x1)) ** 2 + (int(y0) - int(y1)) ** 2) ** 0.5 * 10.0 / 100.0
    assert w.tt[0][1] == pytest.approx(km / 30.0 * 60.0, rel=1e-12)
    assert w.tt[0][0] == 0.0 and w.tt[3][5] == w.tt[5][3]


def test_arrival_rate_matches_the_base_rate_on_average():
    counts = [len(World(s, 10.0, 20, 50)._t) for s in range(1, 21)]
    assert 640 < sum(counts) / len(counts) < 800      # 120 je Stunde mal 6 Stunden = 720 erwartet
