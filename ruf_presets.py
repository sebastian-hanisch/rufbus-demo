"""Permalink (Begrenzen), Presets und Zufalls-Seed-Button (Standardmuster aus dem Demo-Portfolio)."""

import random
from dataclasses import dataclass

import streamlit as st

import ruf_constants as C


@dataclass(frozen=True)
class SettingSpec:
    url_param: str
    caster: type
    default: object
    lo: float | None = None
    hi: float | None = None
    options: tuple | None = None     # Auswahl-Regler: nur diese Werte sind gültig (die Reihe wurde nur auf diesen Stufen gemessen)


SETTING_SPECS = {
    "lam_select": SettingSpec("lam", int, C.DEFAULTS["lam"], options=C.LAM_STEPS),
    "area_select": SettingSpec("area", int, C.DEFAULTS["area"], options=C.AREA_STEPS),
    "stops_select": SettingSpec("stops", int, C.DEFAULTS["stops"], options=C.STOP_STEPS),
    "wait_select": SettingSpec("wait", int, C.DEFAULTS["wait"], options=C.WAIT_STEPS),
    "detour_select": SettingSpec("detour", float, C.DEFAULTS["detour"], options=C.DETOUR_STEPS),
    "cap_select": SettingSpec("cap", int, C.DEFAULTS["cap"], options=C.CAP_STEPS),
    "hub_select": SettingSpec("hub", int, C.DEFAULTS["hub"], options=C.HUB_STEPS),
    "proc_select": SettingSpec("proc", str, "fcfs", options=("fcfs", "ols", "batch")),
    "measure_select": SettingSpec("measure", str, "wait", options=("wait", "t30", "t35", "t40", "t45")),
    "design_select": SettingSpec("design", str, "best", options=("best", "R", "S2", "P1")),
    "seed_input": SettingSpec("seed", int, C.DEFAULT_SEED, 0, C.SEED_MAX),
}
PRESET_KEYS = {
    "lam": "lam_select", "area": "area_select", "stops": "stops_select", "wait": "wait_select", "detour": "detour_select", "cap": "cap_select",
    "hub": "hub_select", "proc": "proc_select", "measure": "measure_select", "design": "design_select", "seed": "seed_input",
}


def init_session_state_defaults():
    for state_key, spec in SETTING_SPECS.items():
        if state_key not in st.session_state:
            st.session_state[state_key] = spec.default


def bounds(state_key):
    spec = SETTING_SPECS[state_key]
    return spec.lo, spec.hi


def clean_value(spec, value):
    """Einen eingelesenen Wert auf den gültigen Bereich bringen: Auswahl-Regler nur auf Stufen (sonst Standard), Zahlen-Regler begrenzt;
    NaN, Infinity und Unlesbares fallen auf den Standard."""
    try:
        value = spec.caster(value)
    except (ValueError, TypeError, OverflowError):
        return spec.default
    if isinstance(value, float) and value != value:        # NaN
        return spec.default
    if isinstance(value, float) and value in (float("inf"), float("-inf")):
        return spec.default
    if spec.options is not None:
        return value if value in spec.options else spec.default
    if spec.lo is not None:
        value = max(spec.lo, value)
    if spec.hi is not None:
        value = min(spec.hi, value)
    return value


def allowed_lams(area):
    """Anfragen je Stunde, die zum Gebiet passen: im 6 × 6-km-Gebiet reicht die gemessene Dichte (bis 1,0 je km²) nur bis 36 Anfragen je Stunde."""
    return tuple(v for v in C.LAM_STEPS if area != 6 or v <= 36)


def fix_state():
    """Gebiet und Anfragen je Stunde müssen zusammenpassen (Permalink oder Preset können beides setzen): sonst auf die nächste erlaubte Stufe."""
    area = st.session_state.get("area_select", SETTING_SPECS["area_select"].default)
    ok = allowed_lams(area)
    lam = st.session_state.get("lam_select", SETTING_SPECS["lam_select"].default)
    if lam not in ok:
        st.session_state["lam_select"] = min(ok, key=lambda v: abs(v - lam))


def load_permalink_settings():
    """Einmal je Sitzung: Werte aus der Adresszeile übernehmen, auf die gemessenen Stufen und Reglergrenzen begrenzt."""
    if "permalink_loaded" in st.session_state:
        return
    qp = st.query_params
    for state_key, spec in SETTING_SPECS.items():
        if spec.url_param in qp:
            st.session_state[state_key] = clean_value(spec, qp[spec.url_param])
    st.session_state["permalink_loaded"] = True


def sync_query_params(values):
    """`values`: {state_key: aktueller Wert}; die Adresszeile spiegelt die Konfiguration."""
    try:
        for state_key, value in values.items():
            st.query_params[SETTING_SPECS[state_key].url_param] = str(value)
    except Exception:
        pass


def apply_preset(name):
    """Ein Preset setzt JEDEN Regler: was es nicht nennt, bekommt den Standardwert (sonst blieben frühere Änderungen stehen)."""
    for key, state_key in PRESET_KEYS.items():
        st.session_state[state_key] = C.PRESETS[name].get(key, SETTING_SPECS[state_key].default)


def aktives_preset():
    """Name des Presets, dessen Werte GENAU den aktuellen Einstellungen entsprechen, sonst None.

    Zustandslos: verglichen wird jeder Regler aus SETTING_SPECS (ein Preset ohne Eintrag für einen Regler meint dessen
    Standardwert) mit dem Session State. Ein später ergänzter Regler braucht nur seinen Eintrag in SETTING_SPECS,
    dann hebt auch seine Änderung die Markierung auf (tests/test_layout.py prüft das für jeden Regler)."""
    preset_key_of = {state_key: key for key, state_key in PRESET_KEYS.items()}
    for name, preset in C.PRESETS.items():
        if all(
            st.session_state.get(state_key, spec.default) == preset.get(preset_key_of.get(state_key), spec.default)
            for state_key, spec in SETTING_SPECS.items()
        ):
            return name
    return None


def sidebar_presets():
    """Schnellstart oben in der Seitenleiste; das aktive Preset ist hervorgehoben (`type="primary"`)."""
    if not C.PRESETS:
        return
    st.header("🎯 Schnellstart")
    st.caption("Ein Beispielszenario laden:")
    aktiv = aktives_preset()
    for name in C.PRESETS:
        st.button(
            name, width="stretch", on_click=apply_preset, args=(name,), help=C.PRESET_HELP.get(name, ""), key=f"preset_{name}",
            type="primary" if aktiv == name else "secondary",
        )


def randomize_seed():
    st.session_state["seed_input"] = random.randint(0, C.SEED_MAX)
