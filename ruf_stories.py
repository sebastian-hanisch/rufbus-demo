"""Abnahmekriterien der Presets: Jedes Preset erzählt eine Geschichte, und die muss auf dem gezeigten Szenario stimmen.

`check(name, a, a_ref)` bekommt die Analyse des Presets (`a`) und, wo ein Vergleich nötig ist, dieselbe Analyse mit Basis-Einstellung (`a_ref`).
Die Schwellen stehen hier einzeln, damit `tests/test_stories.py` jede mit künstlichen Werten an ihrer Grenze prüfen kann."""

import ruf_evaluation as ev
from ruf_sim import INF

# Schwellen
RATIO_THIN = 0.5            # dünn besiedelt: Rufbus höchstens halb so teuer
K_THIN_MAX = 4
GLEICH_LO, GLEICH_HI = 0.9, 1.1
RIDE_GAP_MIN = 10.0         # am Kipppunkt: Linienbus-Reisezeit mindestens so viele Minuten länger
RATIO_DENSE = 1.3
SHARED_DENSE = 0.85
RATIO_AREA = (0.7, 1.3)


def _ratio(a):
    return a.ratio if a.ratio is not None else None


def check_kipppunkt(a, a_ref=None):
    r = _ratio(a)
    return r is not None and GLEICH_LO <= r <= GLEICH_HI and (a.line.get("total", 0) - a.ruf["total"]) >= RIDE_GAP_MIN


def check_duenn(a, a_ref=None):
    r = _ratio(a)
    return a.K != INF and a.K <= K_THIN_MAX and (r is not None and r < RATIO_THIN or a.line_cost == INF)


def check_dicht(a, a_ref=None):
    r = _ratio(a)
    return r is not None and r > RATIO_DENSE and a.ruf["shared"] >= SHARED_DENSE


def check_reisezeit(a, a_ref=None):
    """Beide Formen halten eine mittlere Reisezeit ein: der Rufbus ist billiger, der Linienbus braucht mehr Fahrzeuge (oder erreicht das Maß nie)."""
    return a.verdict == "ruf" and (a.N == INF or a.N > a.K)


def check_wartezeit(a, a_ref):
    """Strengere Wartezeit (10 statt 15 min) bei gleichem Zufalls-Seed: Der Rufbus steht im Kostenvergleich besser da als bei 15 min,
    und der Linienbus ist nicht billiger als der Rufbus (Verhältnis kleiner als in der Basis und unter 1)."""
    r, r0 = _ratio(a), _ratio(a_ref)
    return r is not None and r0 is not None and r < r0 and r < 1.0


def check_gebiet(a, a_ref=None):
    r = _ratio(a)
    return r is not None and RATIO_AREA[0] <= r <= RATIO_AREA[1]


CRITERIA = {
    "Am Kipppunkt": check_kipppunkt,
    "Dünn besiedelt": check_duenn,
    "Dicht besiedelt": check_dicht,
    "Gleiche Reisezeit": check_reisezeit,
    "Kurze Wartezeit": check_wartezeit,
    "Großes Gebiet": check_gebiet,
}
NEEDS_REFERENCE = {"Kurze Wartezeit"}


def settings_of(preset, seed=None):
    """Einstellungen eines Presets (Schlüssel wie in ruf_constants.PRESETS); `seed` überschreibt den Zufalls-Seed des Presets."""
    fields = {k: v for k, v in preset.items() if k != "seed"}
    if "wait" in fields:
        fields["wait"] = float(fields["wait"])
    return ev.Settings(**fields, seed=preset["seed"] if seed is None else seed)


def reference_settings(settings: ev.Settings) -> ev.Settings:
    """Dieselbe Einstellung mit der Basis-Wartezeit (15 min), für den Vergleich im Preset „Kurze Wartezeit“."""
    return ev.Settings(**{**settings.__dict__, "wait": 15.0})


def check(name, a, a_ref=None):
    return bool(CRITERIA[name](a, a_ref))
