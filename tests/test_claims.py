"""Jede Zahl der README (Abschnitt „Befunde“ und „Methodik“) ist hier aus data/ruf_results.json nachgerechnet (DEMO-PLAYBOOK §4)."""

import math
import os
import re
from pathlib import Path

import pytest

import ruf_results as R

ROOT = Path(__file__).resolve().parent.parent
README = (ROOT / "README.md").read_text(encoding="utf-8")
D = R.load()
BASE = R.variants()[0]


def v(part):
    return R.variant_by_label(part)


def de(x, digits=2):
    return f"{x:.{digits}f}".replace(".", ",")


def test_the_readme_mentions_every_number_it_checks_here():
    for text in ("2,6 Fahrzeugen", "14,3", "λ^0,49", "0,85 auf 0,15", "Faktor 5,5", "0,44 Anfragen je km² und Stunde", "44 je Stunde", "Bootstrap 0,42 bis 0,46",
                 "0,65", "0,54", "53 %", "0,52", "0,25", "7,9 min", "31,9 min", "39,8 min", "61 Anfragen/h bei 10 min", "28 bei 25", "−0,20 ± 0,10", "−0,93 ± 0,10",
                 "+7,2 Fahrzeuge", "17 %", "91 %", "33 %", "78 %", "87 %", "0 von 930"):
        assert text in README, text


def test_flotte_scaling_and_cost_per_passenger():
    rows = D["ruf_base"]
    assert de(rows[0]["K_mean"], 1) == "2,6" and de(rows[-1]["K_mean"], 1) == "14,3"
    assert de(D["power_law_exponent"], 2) == "0,49"
    assert de(rows[0]["cost"][0], 2) == "0,85" and de(rows[-1]["cost"][0], 2) == "0,15"
    assert de(rows[0]["cost"][0] / rows[-1]["cost"][0], 1) == "5,5"


def test_base_crossing_and_the_line_designs():
    assert de(BASE["crossing"]) == "0,44" and f"{BASE['lam_cross']:.0f}" == "44"
    assert (de(BASE["boot_p10"]), de(BASE["boot_p90"])) == ("0,42", "0,46")
    assert de(BASE["crossing_fixed"]) == "0,65"                     # eine Linie über alle Haltepunkte (Entwurf R)
    by = BASE["crossing_by_design"]
    assert de(by["R"]) == "0,65" and de(by["P1"]) == "0,54"
    assert all(by[d] == math.inf for d in ("S1", "S2", "S3", "S4", "P2"))


def test_quality_measures():
    assert v("<= 25 min")["crossing"] == math.inf and v("<= 30 min")["crossing"] == math.inf
    t35 = v("Reisezeit <= 35 min")
    assert t35["crossing"] == math.inf and f"{100 * t35['boot_share_none']:.0f}" == "53"
    assert de(v("Reisezeit <= 40 min")["crossing"]) == "0,52" and de(v("Reisezeit <= 45 min")["crossing"]) == "0,25"


def test_line_passenger_pays_in_ride_time():
    rb = D["ruf_base"][6]
    lq = D["line_quality_R"][6]
    assert rb["dens"] == 0.4 and lq["dens"] == 0.4
    assert (de(lq["wait"], 1), de(rb["wait"], 1)) == ("7,9", "8,4")
    assert (de(lq["ride"], 1), de(rb["ride"], 1)) == ("31,9", "12,6")
    assert (de(lq["total"], 1), de(rb["total"], 1)) == ("39,8", "21,0")


def test_area_and_wait_variants():
    assert f"{v('Gebiet 16x16')['lam_cross']:.0f}" == "48" and v("Gebiet 6x6")["crossing"] == math.inf
    assert f"{v('W=10')['lam_cross']:.0f}" == "61" and f"{v('W=25')['lam_cross']:.0f}" == "28"
    assert de(v("GEFAHRENEN")["crossing"]) == "0,54"


def test_procedures():
    batch = [p["diff_mean"] for p in D["proc_vs_fcfs"]["batch"]]
    assert de(min(batch), 1) == "0,3" and de(max(batch), 1) == "1,3" and min(batch) > 0
    b10 = [D["batchB"][k][0] for k in ("10_0.2", "10_0.4", "10_0.8")]
    assert (de(min(b10), 1), de(max(b10), 1)) == ("2,8", "3,9")
    ols = {p["dens"]: p["diff_mean"] for p in D["proc_vs_fcfs"]["ols"]}
    assert (de(-ols[0.8]), de(-ols[1.0])) == ("0,47", "0,60")
    assert max(-x for d, x in ols.items() if d <= 0.6) <= 0.275 and de(-ols[0.6]) == "0,27"


def test_places_detour_pooling():
    last = D["cap_f"][-1]
    assert last["dens"] == 1.0
    assert (de(last["c8_f1.5"][0]), de(last["c8_f1.5"][1], 1)) == ("-0,20", "0,1")
    assert (de(last["c4_f2.0"][0]), de(last["c4_f2.0"][1], 1)) == ("-0,93", "0,1")
    assert de(last["c1_f1.5"][0], 1) == "7,2"
    sh = [p["c4_f1.5"]["shared"] for p in D["pooling"]]
    assert (f"{100 * sh[0]:.0f}", f"{100 * sh[-1]:.0f}") == ("17", "91")
    assert f"{100 * D['pool_effect'][-1]['saving_c4_vs_c1']:.0f}" == "33"


def test_exact_lot():
    e = D["exact"]["8_1_0_15"]
    assert (f"{100 * e['fcfs']['served_rel']:.0f}", f"{100 * e['batch']['served_rel']:.0f}") == ("78", "87")
    assert D["exact_checks"]["heur_beats_exact"] == 0 and D["exact_checks"]["rows"] == 930
    assert D["exact_checks"]["incomplete"] == 0


def test_measurement_size_and_file_size():
    m = D["meta"]
    assert (m["n_runs"], m["n_cells"], m["n_line_rows"], m["n_exact_instances"]) == (60051, 202, 14700, 930)
    assert os.path.getsize(ROOT / "data" / "ruf_results.json") < 150 * 1024


def test_the_mutation_list_has_36_entries():
    text = (ROOT / "tools" / "mutation_check.py").read_text(encoding="utf-8")
    entries = re.findall(r'^    \("ruf_[a-z]+\.py", ', text, flags=re.M)
    assert len(entries) == 36 and "36 Rechenstellen" in README
