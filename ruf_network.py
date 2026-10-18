"""Szenario: ganzzahliger Haltepunkt- und Nachfragegenerator und der verdünnbare Anfragenstrom (Welt einer Instanz).

Alles, was Entscheidungen beeinflusst, kommt aus Ganzzahlen (SplitMix64, Raster 5..95, ganzzahlige Nachfragegewichte); Entfernungen und
Fahrzeiten entstehen aus `sqrt` und Multiplikation (IEEE-exakt gerundet), nicht aus Bibliotheksfunktionen mit plattformabhängigen Ergebnissen.
"""

import math
from bisect import bisect_right

import numpy as np

import ruf_constants as C
from ruf_rng import SplitMix64

_STREAM = {"arrival": 1, "od": 2, "thin": 3, "start": 4}


def _stream(seed, name):
    return SplitMix64(int(seed) + (_STREAM[name] << 40))


def generate_network(n_stops, seed, hub_pct=50, n_hubs=2):
    """Ganzzahlige Haltepunkte (Raster 5..95) und symmetrische ganzzahlige Nachfrage. hub_pct = Hub-Konzentration in Prozent:
    Zeilen und Spalten der Hubs bekommen den Faktor 1 + 6 * hub_pct / 100 (50 entspricht dem Faktor 4 der Liniennetz-Demo)."""
    rng = SplitMix64(seed)
    coords = np.array([[C.GRID_LO + rng.below(C.GRID_SPAN), C.GRID_LO + rng.below(C.GRID_SPAN)] for _ in range(n_stops)], dtype=np.int64)
    base = [[0] * n_stops for _ in range(n_stops)]
    for i in range(n_stops):
        for j in range(i + 1, n_stops):
            base[i][j] = base[j][i] = 1 + rng.below(10)
    pool = list(range(n_stops))
    hubs = [pool.pop(rng.below(len(pool))) for _ in range(max(1, min(n_hubs, n_stops)))]
    boost = 100 + 6 * hub_pct
    b = [boost if i in hubs else 100 for i in range(n_stops)]
    demand = np.zeros((n_stops, n_stops), dtype=np.int64)
    for i in range(n_stops):
        for j in range(n_stops):
            if i != j:
                demand[i, j] = (base[i][j] * b[i] * b[j] + 5000) // 10000
    return coords, demand, hubs


class World:
    """Haltepunkte, Fahrzeiten, Nachfragematrix und der (verdünnbare) Anfragenstrom einer Instanz."""

    def __init__(self, seed, L=10.0, n_stops=30, hub_pct=50):
        self.seed, self.L, self.n, self.hub_pct = int(seed), float(L), int(n_stops), int(hub_pct)
        grid, demand, self.hubs = generate_network(self.n, self.seed, self.hub_pct)
        self.grid = grid
        self.demand = demand
        scale = self.L / 100.0
        self.coords = grid * scale
        n = self.n
        sq = [[int((grid[i][0] - grid[j][0]) ** 2 + (grid[i][1] - grid[j][1]) ** 2) for j in range(n)] for i in range(n)]
        self.dist = np.array([[math.sqrt(s) * self.L / 100.0 for s in row] for row in sq])
        self.sq = sq
        self.tt = [[d / C.V_KMH * 60.0 for d in row] for row in self.dist.tolist()]
        self.ttm = np.array(self.tt)
        self.hub = int(np.argmax(demand.sum(axis=1)))
        # Anfragenstrom: je Sekunde des Betriebstages ein Bernoulli-Versuch mit p = LAM_MAX / 3600 (ganzzahlige Schwelle)
        arr = _stream(self.seed, "arrival")
        od = _stream(self.seed, "od")
        thin = _stream(self.seed, "thin")
        thr = int(C.LAM_MAX / 3600.0 * 2 ** 32)
        flat = [int(v) for v in demand.reshape(-1)]
        cum, s = [], 0
        for v in flat:
            s += v
            cum.append(s)
        total = s
        self._t, self._o, self._d, self._u = [], [], [], []
        for sec in range(int(C.T_TOTAL * 60)):
            if arr.u32() < thr:
                idx = bisect_right(cum, od.below(total))
                self._t.append(sec / 60.0)
                self._o.append(idx // n)
                self._d.append(idx % n)
                self._u.append(thin.u32())
        st = _stream(self.seed, "start")
        self.starts = [st.below(n) for _ in range(64)]

    def requests(self, lam):
        """Anfragen (Zeit in min, Start, Ziel) bei Rate lam je Stunde: Teilmenge des Basis-Stroms (Verdünnung per Ganzzahl-Schwelle)."""
        thr = int(float(lam) / C.LAM_MAX * 2 ** 32)
        return [(t, o, d) for t, o, d, u in zip(self._t, self._o, self._d, self._u) if u < thr]
