"""Live-Szenario: Einstellungen, Rufbus-Flotte K*, Linienbus-Fahrzeugzahl N*, Kosten je Fahrgast, Reisezeiten und Verdikt in drei Zuständen."""

from dataclasses import dataclass, field

import ruf_constants as C
import ruf_search as S
from ruf_line import DESIGNS
from ruf_network import World
from ruf_sim import INF, summarize

DESIGN_OPTIONS = ("best", "R", "S2", "P1")
DESIGN_LABEL = {
    "best": "bester Entwurf je Szenario",
    "R": "eine Linie über alle Haltepunkte",
    "S1": "Sternnetz mit 1 Linie",
    "S2": "Sternnetz mit 2 Linien",
    "S3": "Sternnetz mit 3 Linien",
    "S4": "Sternnetz mit 4 Linien",
    "P1": "Teilabdeckung (Fußweg bis 1,0 km)",
    "P2": "Teilabdeckung (Fußweg bis 1,5 km)",
}
MEASURE_OPTIONS = ("wait", "t30", "t35", "t40", "t45")
MEASURE_LABEL = {
    "wait": "gleiche mittlere Wartezeit",
    "t30": "mittlere Gesamtreisezeit höchstens 30 min (beide)",
    "t35": "mittlere Gesamtreisezeit höchstens 35 min (beide)",
    "t40": "mittlere Gesamtreisezeit höchstens 40 min (beide)",
    "t45": "mittlere Gesamtreisezeit höchstens 45 min (beide)",
}
MEASURE_THETA = {"t30": 30.0, "t35": 35.0, "t40": 40.0, "t45": 45.0}
PROC_OPTIONS = ("fcfs", "ols", "batch")
PROC_LABEL = {"fcfs": "sofortige Einfügung", "ols": "Einfügen + Verbessern", "batch": "Batch (Fenster 5 min)"}
EQUAL_BAND = 0.1     # Verhältnis innerhalb 1 ± 0,1 gilt als "etwa gleich teuer"


@dataclass(frozen=True)
class Settings:
    lam: int = C.DEFAULTS["lam"]
    area: int = C.DEFAULTS["area"]
    stops: int = C.DEFAULTS["stops"]
    wait: float = float(C.DEFAULTS["wait"])
    detour: float = C.DEFAULTS["detour"]
    cap: int = C.DEFAULTS["cap"]
    hub: int = C.DEFAULTS["hub"]
    proc: str = "fcfs"
    measure: str = "wait"
    design: str = "best"
    seed: int = C.DEFAULT_SEED

    @property
    def density(self):
        return self.lam / (self.area * self.area)


@dataclass
class Analysis:
    settings: Settings
    world: World
    sim: object                      # Rufbus-Lauf bei K*
    K: float                         # Flotte Rufbus (inf, wenn nie erreicht)
    ruf: dict                        # Kennzahlen des Rufbusses bei K*
    ruf_cost: float                  # Fahrzeugstunden je bedientem Fahrgast
    design: str                      # gewählter Linienentwurf (bei "best": der günstigste)
    N: float                         # Fahrzeuge Linienbus (inf, wenn nie erreicht)
    line: dict                       # Kennzahlen des Linienbusses bei N
    line_cost: float
    lines: list                      # Linie-Objekte des gewählten Entwurfs
    by_design: dict = field(default_factory=dict)   # Entwurf -> (N, Kosten)
    time_s: float = 0.0

    @property
    def ratio(self):
        if self.line_cost == INF or self.ruf_cost == INF:
            return None
        return self.ruf_cost / self.line_cost

    @property
    def verdict(self):
        """Drei Zustände: 'ruf' (Rufbus billiger), 'line' (Linienbus billiger), 'gleich' (Verhältnis innerhalb 1 +- EQUAL_BAND).
        Ist der Linienbus nicht erreichbar, gewinnt der Rufbus; ist der Rufbus nicht erreichbar, der Linienbus."""
        if self.ruf_cost == INF and self.line_cost == INF:
            return "keiner"
        if self.line_cost == INF:
            return "ruf"
        if self.ruf_cost == INF:
            return "line"
        r = self.ratio
        if r < 1 - EQUAL_BAND:
            return "ruf"
        if r > 1 + EQUAL_BAND:
            return "line"
        return "gleich"


def build_world(s: Settings) -> World:
    return World(s.seed, float(s.area), s.stops, s.hub)


def ruf_part(world: World, s: Settings):
    """Rufbus: Flotte K* (kleinste Flotte mit Servicegrad >= 90 %, optional mittlere Gesamtzeit <= theta), Kennzahlen und Kosten."""
    rows = S.scan_ruf(world, float(s.lam), s.cap, s.wait, s.detour, proc=s.proc, search_seed=s.seed * 100)
    theta = MEASURE_THETA.get(s.measure)
    K, row = S.kstar(rows, theta=theta)
    if row is None:
        return INF, None, INF, None
    sim = S.run_ruf(world, float(s.lam), int(K), s.cap, s.wait, s.detour, proc=s.proc, search_seed=s.seed * 100, improve=(s.proc != "batch0"))
    return K, row, S.ruf_cost(row, K), sim


def line_predicate(s: Settings, ruf_row):
    if s.measure == "wait":
        return S.line_pred("wait", ruf_row["wait"])
    return S.line_pred("total", MEASURE_THETA[s.measure])


def line_part(world: World, s: Settings, ruf_row, line_res_for):
    """Linienbus: kleinste Fahrzeugzahl N* je Entwurf bei gleichem Qualitätsmaß; `line_res_for(design)` liefert (res, lines, access)."""
    designs = DESIGNS if s.design == "best" else [s.design]
    pred = line_predicate(s, ruf_row)
    by_design, best = {}, None
    for d in designs:
        res, lines, _acc = line_res_for(d)
        N = S.nstar_line(res, pred)
        cost = S.line_cost(N, ruf_row["n_req"], res[N]["reach"]) if N != INF else INF
        by_design[d] = (N, cost)
        if best is None or cost < best[1]:
            best = (d, cost, N, res, lines)
    d, cost, N, res, lines = best
    return d, N, (res[N] if N != INF else None), cost, lines, by_design


def analyse(s: Settings, line_res_for=None) -> Analysis:
    """Ein Szenario. `line_res_for` darf zwischengespeichert sein (App: st.cache_data je Entwurf); ohne Angabe wird direkt gerechnet."""
    import time

    t0 = time.perf_counter()
    world = build_world(s)
    K, row, cost, sim = ruf_part(world, s)
    if row is None:
        return Analysis(s, world, None, INF, {}, INF, "R", INF, {}, INF, [], {}, time.perf_counter() - t0)
    reqs = world.requests(float(s.lam))
    if line_res_for is None:
        def line_res_for(d):
            return S.line_summaries(world, d, reqs, s.seed)
    d, N, lrow, lcost, lines, by_design = line_part(world, s, row, line_res_for)
    return Analysis(s, world, sim, K, row, cost, d, N, lrow or {}, lcost, lines, by_design, time.perf_counter() - t0)
