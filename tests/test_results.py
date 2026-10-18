"""Vorgerechnete Messreihe (data/ruf_results.json): Aufbau, innere Konsistenz und Bitgleichheit der Live-Rechnung gegen die Sweeps."""

import math

import pytest

import ruf_results as R
import ruf_search as S
from ruf_network import World
from ruf_sim import INF

DENS = [0.03, 0.06, 0.1, 0.15, 0.2, 0.3, 0.4, 0.6, 0.8, 1.0]


def test_the_base_table_has_the_ten_measured_densities_and_30_seeds_per_cell():
    assert R.densities() == DENS
    m = R.meta()
    assert m["seeds"] == [1, 30] and m["seeds_per_cell"] == {"30": m["n_cells"]}
    assert m["generator"].startswith("ganzzahlig")


def test_flotte_mean_equals_the_mean_of_the_per_seed_values():
    for row in R.base_rows():
        ks = R.ks_by_seed(row["dens"])["K"]
        assert len(ks) == 30
        assert sum(ks) / 30 == pytest.approx(row["K_mean"], abs=1e-4)   # Datei rundet auf 6 gültige Stellen


def test_flotte_grows_slower_than_demand_and_cost_per_passenger_falls():
    rows = R.base_rows()
    ks = [r["K_mean"] for r in rows]
    assert all(b > a for a, b in zip(ks, ks[1:]))
    costs = [r["cost"][0] for r in rows]
    assert all(b < a for a, b in zip(costs, costs[1:]))
    slope = (math.log(ks[-1]) - math.log(ks[0])) / (math.log(rows[-1]["lam"]) - math.log(rows[0]["lam"]))
    assert 0.4 < slope < 0.6


def test_the_base_crossing_is_inside_its_bootstrap_band_and_matches_lambda():
    c = R.variants()[0]
    assert c["boot_p10"] <= c["crossing"] <= c["boot_p90"]
    assert c["lam_cross"] == pytest.approx(c["crossing"] * 100, rel=1e-6)


def test_every_variant_has_curves_for_all_designs_and_consistent_lengths():
    for c in R.variants():
        n = len(c["ruf_mean"])
        assert len(c["line_mean_oracle"]) == n and len(c["line_mean_fixed"]) == n
        assert set(c["line_mean_by_design"]) == {"R", "S1", "S2", "S3", "S4", "P1", "P2"}
        assert all(len(v) == n for v in c["line_mean_by_design"].values())
        for key in ("crossing", "crossing_fixed", "crossing_cell"):
            assert isinstance(c[key], float)           # auch ±Unendlich ist eine Zahl (aus "inf" / "-inf" gelesen)


def test_ratio_bands_are_ordered_and_cover_the_densities():
    for measure, per_design in R.load()["ratio_band"].items():
        for design, b in per_design.items():
            assert len(b["D"]) == 10
            for lo, med, hi in zip(b["p10"], b["med"], b["p90"]):
                assert lo <= med <= hi, (measure, design)


def test_band_lookup_finds_the_nearest_density_and_rejects_far_ones():
    assert R.band_for("wait", "best", 0.4) is not None
    assert R.band_for("wait", "best", 0.41) == R.band_for("wait", "best", 0.4)
    assert R.band_for("wait", "best", 3.0) is None and R.band_for("unbekannt", "best", 0.4) is None


@pytest.mark.parametrize("dens, seeds", [(0.1, (1, 2, 3)), (0.4, (1, 2, 3, 30))])
def test_live_scan_equals_the_sweep_per_seed(dens, seeds):
    """Ein Live-Szenario mit Zufalls-Seed s liefert exakt dieselben K* und N* wie die Messreihe für diesen Zufalls-Seed."""
    tab = R.ks_by_seed(dens)
    for s in seeds:
        w = World(s, 10.0, 30, 50)
        lam = S.lam_of(dens, 10.0)
        rows = S.scan_ruf(w, lam, 4, 15.0, 1.5, "fcfs")
        K, row = S.kstar(rows)
        i = tab["seeds"].index(s)
        assert K == tab["K"][i], (dens, s)
        res, _, _ = S.line_summaries(w, "R", w.requests(lam), s)
        N = S.nstar_line(res, S.line_pred("wait", row["wait"]))
        assert (N if N != INF else INF) == tab["N_R"][i], (dens, s)
