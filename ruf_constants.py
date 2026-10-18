"""Konstanten: Modellannahmen, Reglerstufen, Farben und Presets."""

# --- Modell (feste Annahmen, im Regler nicht veränderbar; Annahmen-Tabelle in der App) -------------------------------------------------------
V_KMH = 30.0            # Fahrgeschwindigkeit in km/h (Luftlinie)
DWELL = 0.5             # min je Halt (Aufnahme oder Absetzen)
SLACK = 2.0             # min fester Aufschlag auf die Umweggrenze
EPS = 1e-9
T_TOTAL = 360.0         # Betriebstag in min
T0_MEAS, T1_MEAS = 45.0, 315.0   # Messfenster: Anlauf 45 min und Auslauf 45 min nicht gemessen
MEAS_HOURS = (T1_MEAS - T0_MEAS) / 60.0   # 4,5 h
LAM_MAX = 120.0         # Anfragen/h des Basis-Stroms; kleinere Raten sind eine Teilmenge (Verdünnung)
SERVICE_TARGET = 0.9    # Servicegrad, ab dem die Flotte reicht
LAYOVER = 2.0           # min Wende am Linienende
TRANSFER = 1.0          # min Umstiegsweg
CAP_LINE = 40           # Plätze Linienbus (nur Lastcheck)
WALK_KMH = 5.0
GRID_LO, GRID_SPAN = 5, 91   # Haltepunkte liegen auf dem Raster 5..95 (ganzzahlig), skaliert auf das Gebiet

# --- Regler -------------------------------------------------------------------------------------------------------------------------------
LAM_STEPS = (3, 6, 10, 15, 20, 30, 40, 60, 80, 100)   # Anfragen je Stunde (gemessene Stufen bei Gebiet 10 km)
AREA_STEPS = (6, 10, 16)
STOP_STEPS = (20, 30, 40)
WAIT_STEPS = (10, 15, 25)
DETOUR_STEPS = (1.5, 2.0)
CAP_STEPS = (1, 2, 4, 8)
HUB_STEPS = (0, 50, 100)    # Hub-Konzentration in Prozent (0 = gleichverteilt)
SEED_MAX, DEFAULT_SEED = 9999, 505
DEFAULTS = dict(lam=40, area=10, stops=30, wait=15, detour=1.5, cap=4, hub=50)

COLOR_RUF = "#1f6fb2"
COLOR_LINE = "#c77700"
COLOR_LINE_R = "#c0392b"
COLOR_STOP = "rgba(90,100,120,0.8)"

# Zufalls-Seeds der Presets: `tools/preset_search.py` wählt den ersten Zufalls-Seed ab 500 (außerhalb der Stichprobe 1 bis 30 der Messreihe), auf dem die Geschichte des Presets nach ruf_stories.py stimmt.
PRESETS = {
    "Am Kipppunkt": {"lam": 40, "seed": 505},          # das erste Preset ist die Voreinstellung (tests/test_layout.py)
    "Dünn besiedelt": {"lam": 6, "seed": 500},
    "Dicht besiedelt": {"lam": 100, "seed": 500},
    "Gleiche Reisezeit": {"lam": 40, "measure": "t30", "seed": 500},
    "Kurze Wartezeit": {"lam": 40, "wait": 10, "seed": 500},
    "Großes Gebiet": {"lam": 40, "area": 16, "seed": 500},
}
PRESET_HELP = {
    "Dünn besiedelt": "6 Anfragen pro Stunde: wenige Fahrtwünsche, der Rufbus braucht nur wenige Fahrzeuge, der Linienbus für dieselbe Wartezeit viele.",
    "Am Kipppunkt": "40 Anfragen pro Stunde: bei gleicher mittlerer Wartezeit etwa gleich teuer, aber die Reisezeit unterscheidet sich stark.",
    "Dicht besiedelt": "100 Anfragen pro Stunde: bei gleicher Wartezeit gewinnt der Linienbus die Kostenrechnung; das Bündeln spart dem Rufbus viel Flotte.",
    "Gleiche Reisezeit": "40 Anfragen pro Stunde, beide Formen sollen im Mittel höchstens 30 Minuten unterwegs sein: Der Linienbus braucht mehr Fahrzeuge.",
    "Kurze Wartezeit": "40 Anfragen pro Stunde, Rufbus-Zusage nur bis 10 Minuten Wartezeit: das strengere Versprechen verschiebt den Kipppunkt.",
    "Großes Gebiet": "40 Anfragen pro Stunde auf 16 × 16 km: dünner besiedelt, in Anfragen je Stunde bleibt der Kipppunkt aber ähnlich.",
}
