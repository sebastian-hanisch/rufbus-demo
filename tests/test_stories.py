"""Presets erzählen ihre Geschichte: jedes Kriterium aus ruf_stories.py gilt auf dem gezeigten Szenario und kippt an seiner Schwelle (künstliche Werte)."""

from types import SimpleNamespace

import pytest

import ruf_constants as C
import ruf_evaluation as ev
import ruf_stories as ST
from ruf_sim import INF


def fake(ratio=1.0, K=7, N=8, shared=0.5, ruf_total=20.0, line_total=40.0, verdict=None, line_cost=1.0):
    ruf_cost = None if ratio is None else ratio * line_cost
    a = SimpleNamespace(K=K, N=N, ruf={"shared": shared, "total": ruf_total}, line={"total": line_total}, line_cost=line_cost, ratio=ratio, ruf_cost=ruf_cost)
    a.verdict = verdict or ("ruf" if ratio is not None and ratio < 0.9 else "line" if ratio is not None and ratio > 1.1 else "gleich")
    return a


@pytest.mark.parametrize("name", list(C.PRESETS))
def test_every_preset_story_holds_on_the_shown_scenario(name):
    s = ST.settings_of(C.PRESETS[name])
    a = ev.analyse(s)
    ref = ev.analyse(ST.reference_settings(s)) if name in ST.NEEDS_REFERENCE else None
    assert ST.check(name, a, ref), (name, a.ratio, a.K, a.N)


def test_preset_seeds_are_outside_the_sample_of_the_measurement_series():
    assert all(p["seed"] >= 500 for p in C.PRESETS.values()) and C.DEFAULT_SEED >= 500


def test_kipppunkt_thresholds():
    assert ST.check_kipppunkt(fake(ratio=1.0, ruf_total=20, line_total=40))
    assert not ST.check_kipppunkt(fake(ratio=ST.GLEICH_HI + 0.01))
    assert not ST.check_kipppunkt(fake(ratio=ST.GLEICH_LO - 0.01))
    assert not ST.check_kipppunkt(fake(ratio=1.0, ruf_total=20, line_total=20 + ST.RIDE_GAP_MIN - 0.1))


def test_duenn_thresholds():
    assert ST.check_duenn(fake(ratio=0.3, K=ST.K_THIN_MAX))
    assert not ST.check_duenn(fake(ratio=0.3, K=ST.K_THIN_MAX + 1))
    assert not ST.check_duenn(fake(ratio=ST.RATIO_THIN + 0.01, K=3))


def test_dicht_thresholds():
    assert ST.check_dicht(fake(ratio=ST.RATIO_DENSE + 0.01, shared=ST.SHARED_DENSE))
    assert not ST.check_dicht(fake(ratio=ST.RATIO_DENSE, shared=1.0))
    assert not ST.check_dicht(fake(ratio=2.0, shared=ST.SHARED_DENSE - 0.01))


def test_reisezeit_requires_a_cheaper_rufbus_and_a_bigger_line_fleet():
    assert ST.check_reisezeit(fake(ratio=0.5, K=8, N=20))
    assert ST.check_reisezeit(fake(ratio=0.5, K=8, N=INF))
    assert not ST.check_reisezeit(fake(ratio=0.5, K=8, N=8))
    assert not ST.check_reisezeit(fake(ratio=1.0, K=8, N=20))


def test_wartezeit_compares_with_the_reference_wait():
    assert ST.check_wartezeit(fake(ratio=0.8), fake(ratio=0.9))
    assert not ST.check_wartezeit(fake(ratio=0.95), fake(ratio=0.9))
    assert not ST.check_wartezeit(fake(ratio=1.05), fake(ratio=1.2))


def test_gebiet_thresholds():
    lo, hi = ST.RATIO_AREA
    assert ST.check_gebiet(fake(ratio=lo)) and ST.check_gebiet(fake(ratio=hi))
    assert not ST.check_gebiet(fake(ratio=lo - 0.01)) and not ST.check_gebiet(fake(ratio=hi + 0.01))


def test_every_preset_has_a_criterion():
    assert set(ST.CRITERIA) == set(C.PRESETS)
