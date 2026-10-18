"""Presets: Vollständigkeit, gültige Werte, Standardverhalten, Permalink-Begrenzung (NaN, Infinity, unbekannte Stufen)."""

import ruf_constants as C
import ruf_evaluation as ev
import ruf_presets as P


def test_every_preset_has_help_and_only_known_keys():
    assert set(C.PRESETS) == set(C.PRESET_HELP)
    for name, preset in C.PRESETS.items():
        assert set(preset) <= set(P.PRESET_KEYS), name
        assert "lam" in preset and "seed" in preset, name
        assert C.PRESET_HELP[name]


def test_preset_values_are_valid_steps_and_inside_the_seed_range():
    for name, preset in C.PRESETS.items():
        for key, value in preset.items():
            spec = P.SETTING_SPECS[P.PRESET_KEYS[key]]
            if spec.options is not None:
                assert value in spec.options, (name, key)
            else:
                assert spec.lo <= value <= spec.hi, (name, key)
        area = preset.get("area", C.DEFAULTS["area"])
        assert preset["lam"] in P.allowed_lams(area), name


def test_settings_defaults_equal_the_spec_defaults():
    s = ev.Settings()
    for state_key, spec in P.SETTING_SPECS.items():
        attr = spec.url_param
        assert getattr(s, attr) == spec.default or float(getattr(s, attr)) == float(spec.default), state_key


def test_setting_specs_cover_every_preset_key():
    assert set(P.PRESET_KEYS.values()) == set(P.SETTING_SPECS)


def test_clean_value_limits_and_rejects_garbage():
    lam = P.SETTING_SPECS["lam_select"]
    assert P.clean_value(lam, "40") == 40
    assert P.clean_value(lam, "41") == lam.default            # keine gemessene Stufe
    assert P.clean_value(lam, "abc") == lam.default
    assert P.clean_value(lam, "nan") == lam.default
    assert P.clean_value(lam, "inf") == lam.default
    seed = P.SETTING_SPECS["seed_input"]
    assert P.clean_value(seed, "-5") == 0 and P.clean_value(seed, "99999999") == C.SEED_MAX
    detour = P.SETTING_SPECS["detour_select"]
    assert P.clean_value(detour, "2.0") == 2.0 and P.clean_value(detour, "nan") == detour.default and P.clean_value(detour, "inf") == detour.default
    assert P.clean_value(P.SETTING_SPECS["proc_select"], "zufall") == "fcfs"


def test_allowed_lams_cut_the_small_area():
    assert max(P.allowed_lams(6)) == 30 and P.allowed_lams(10) == C.LAM_STEPS and P.allowed_lams(16) == C.LAM_STEPS
    assert all(v / 36.0 <= 1.0 for v in P.allowed_lams(6))      # Messreihe reicht bis Dichte 1,0 je km²
