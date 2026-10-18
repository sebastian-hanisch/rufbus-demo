"""Mutationsprüfung: jede Änderung an einer Rechenstelle muss mindestens einen Test fehlschlagen lassen.

Aufruf (aus dem Repo-Ordner, mit dem Test-venv): python tools/mutation_check.py [--jobs 4] [--only Teil]
Jeder Mutant läuft in einer Kopie des Repos (Temp-Ordner), die Tests des Kerns (ohne App-Tests) laufen mit -x. Ergebnis: pro Mutant
„gefunden“ (ein Test scheitert) oder „ÜBERLEBT“; Rückgabewert 1, wenn ein Mutant überlebt."""
import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TESTS = ["tests/test_rng.py", "tests/test_network.py", "tests/test_sim.py", "tests/test_search.py", "tests/test_line.py", "tests/test_oracle_rufbus.py"]

# (Datei, alter Text, neuer Text, Beschreibung[, n-te Stelle]); jeder alte Text kommt in der Datei genau einmal vor, sonst mit Stellenangabe.
# Bewusst NICHT in der Liste (gleichwertige Änderungen oder reine Heuristik-Vorlieben, im README begründet):
#  - Umweggrenze am Routenende lockern: beim Einfügen ans Ende ist die Fahrt gleich der Direktfahrt, die Grenze greift nie.
#  - Umlegen auch ohne Ersparnis: die ursprüngliche Position bleibt nach dem Herausnehmen möglich, die beste Position kostet nie mehr als die Ersparnis.
#  - Aufteilung der Fahrzeuge ohne Überschneidungsprüfung (exakt): eine doppelt bediente Anfrage kann bei Dreiecksungleichung nie billiger sein.
#  - Bedauern im Batch ignorieren: nur die Reihenfolge der Einfügung (Heuristik), keine Zulässigkeit.
#  - Kipppunkt bei exakt gleichem Verhältnis und Rundung der Nachfrage bei Zentren-Zuschlägen, die Vielfache von 100 sind (die gemessenen Stufen 0/50/100).
MUTANTS = [
    ("ruf_sim.py", "if Lg[i] + 1 > cap:", "if Lg[i] + 1 > cap + 1:", "Kapazität beim Einfügen lockern"),
    ("ruf_sim.py", "if Lg[j] + 1 > cap:", "if Lg[j] + 1 > cap + 1:", "Kapazität im Innern der Route lockern"),
    ("ruf_sim.py", "self.ddl = [t + W for t in self.rt]", "self.ddl = [t + W + 1.0 for t in self.rt]", "Wartegrenze verlängern"),
    ("ruf_sim.py", "self.rmax = [f * (tt[o][d] + dwell) + slack for _, o, d in reqs]", "self.rmax = [f * tt[o][d] + slack for _, o, d in reqs]", "Umweggrenze ohne Halt"),
    ("ruf_sim.py", "self.rmax = [f * (tt[o][d] + dwell) + slack for _, o, d in reqs]", "self.rmax = [f * (tt[o][d] + dwell) for _, o, d in reqs]", "Umweggrenze ohne Aufschlag"),
    ("ruf_sim.py", "return 1 if (v.ev and v.ta < now - EPS) else 0", "return 0", "gesperrten ersten Halt freigeben"),
    ("ruf_sim.py", "                c = tD + dw - old_end\n                if collect is not None:\n                    collect.append((c, i, i))", "                c = tD - old_end\n                if collect is not None:\n                    collect.append((c, i, i))", "Einfügekosten ohne letzten Halt (Ende der Route)"),
    ("ruf_sim.py", "c = tt[v.loc][p] + dw + tt[p][d] + dw", "c = tt[v.loc][p] + dw + tt[p][d]", "Kosten der leeren Route ohne zweiten Halt"),
    ("ruf_sim.py", "t += tt[loc][s]\n            arr.append(t)", "t += tt[loc][s] * 0.9\n            arr.append(t)", "Fahrzeiten der Route verkürzen"),
    ("ruf_sim.py", "t += dw\n            loc = s\n        v.arr = arr", "t += 0.0\n            loc = s\n        v.arr = arr", "Halt in der Route weglassen"),
    ("ruf_sim.py", "self.busy.append((a - tt[v.loc][s], a + dw))", "self.busy.append((a - tt[v.loc][s], a))", "Haltezeit aus der Fahrzeugzeit entfernen"),
    ("ruf_sim.py", "out[\"wait\"] = sum(w) / len(w)", "out[\"wait\"] = max(w)", "mittlere Wartezeit durch Maximum ersetzen"),
    ("ruf_sim.py", "idx = [r for r in range(sim.n) if t0 <= sim.rt[r] < t1]", "idx = [r for r in range(sim.n) if 0 <= sim.rt[r] < t1]", "Anlauf in die Messung nehmen"),
    ("ruf_sim.py", "out[\"served\"] = len(acc) / len(idx) if idx else 1.0", "out[\"served\"] = len(acc) / (len(idx) + 1) if idx else 1.0", "Servicegrad verfälschen"),
    ("ruf_sim.py", "if after < before - 1e-7:", "if after < before + 1.0:", "Austausch auch bei Verschlechterung annehmen"),
    ("ruf_search.py", "while i > 0 and ok[i - 1]:\n        i -= 1\n    return rows[i][\"K\"], rows[i]", "while i > 0 and ok[i - 1] and i > 1:\n        i -= 1\n    return rows[i][\"K\"], rows[i]", "K* bricht eine Stufe zu früh ab"),
    ("ruf_search.py", "p = r[\"served\"] >= target - 1e-12", "p = r[\"served\"] >= target - 0.2", "Servicegrad-Ziel lockern"),
    ("ruf_search.py", "return K * C.MEAS_HOURS / max(row[\"n_acc\"], 1)", "return K * 4.0 / max(row[\"n_acc\"], 1)", "Messfenster der Kosten"),
    ("ruf_search.py", "return N * C.MEAS_HOURS / (n_req * reach)", "return N * C.MEAS_HOURS / n_req", "Erreichbarkeit aus den Linienkosten streichen"),
    ("ruf_search.py", "x0, x1 = math.log(D[i]), math.log(D[i + 1])", "x0, x1 = D[i], D[i + 1]", "linear statt logarithmisch interpolieren"),
    ("ruf_search.py", "if good >= 3:", "if good >= 2:", "Abbruchregel der Flottensuche"),
    ("ruf_search.py", "good = good + 1 if s[\"served\"] >= 0.95 else 0", "good = good + 1 if s[\"served\"] >= 0.9 else 0", "Abbruchschwelle der Flottensuche"),
    ("ruf_search.py", "rng = SplitMix64(int(seed) * 1000 + 99 * 10 + int(design_index))", "rng = SplitMix64(int(seed) * 1000 + 99 * 10)", "Fahrplanphase unabhängig vom Entwurf"),
    ("ruf_search.py", "return lambda v: v[\"reach\"] >= 0.9 and v.get(\"wait\", INF) <= val + 1e-9 and v[\"rho\"] <= 1.0", "return lambda v: v[\"reach\"] >= 0.9 and v.get(\"wait\", INF) <= val + 5.0 and v[\"rho\"] <= 1.0", "Wartezeit-Maß des Linienbusses lockern"),
    ("ruf_line.py", "taub[P - 1] = T1 + LAYOVER", "taub[P - 1] = T1", "Wendezeit am Linienende streichen"),
    ("ruf_line.py", "self.C = taub[0] + LAYOVER", "self.C = taub[0]", "Wendezeit am Linienanfang streichen"),
    ("ruf_line.py", "k = max(range(m), key=lambda l: (Cs[l] / Nl[l], -l))", "k = min(range(m), key=lambda l: (Cs[l] / Nl[l], l))", "Fahrzeugverteilung umkehren"),
    ("ruf_line.py", "adj[s].append((node, h[l] / 2.0 + 0.0, 1))", "adj[s].append((node, h[l] + 0.0, 1))", "Wartezeit je Einstieg verdoppeln"),
    ("ruf_line.py", "nd += TRANSFER      # Umstieg: Weg zum Bahnsteig", "nd += 0.0", "Umstiegszeit streichen"),
    ("ruf_line.py", "board = base + h[l] * np.ceil((c - base) / h[l] - 1e-12)", "board = base + h[l] * np.floor((c - base) / h[l] - 1e-12)", "Abfahrt vor der Ankunft des Fahrgasts"),
    ("ruf_line.py", "q, r = divmod(len(items), parts)", "q, r = divmod(len(items), parts + 1)", "Aufteilung der Linienäste"),
    ("ruf_line.py", "return -1 if cross > 0 else 1", "return 1 if cross > 0 else -1", "Winkelreihenfolge umkehren"),
    ("ruf_line.py", "while 100 * cov_num(covered) < PARTIAL_COVER_PCT * total", "while 100 * cov_num(covered) < 50 * total", "Abdeckungsziel der Teilabdeckung senken"),
    ("ruf_network.py", "thr = int(C.LAM_MAX / 3600.0 * 2 ** 32)", "thr = int(C.LAM_MAX / 3600.0 * 2 ** 31)", "Ankunftsrate halbieren"),
    ("ruf_network.py", "boost = 100 + 6 * hub_pct", "boost = 100 + 5 * hub_pct", "Zentren-Zuschlag"),
    ("ruf_network.py", "self.tt = [[d / C.V_KMH * 60.0 for d in row] for row in self.dist.tolist()]", "self.tt = [[d / C.V_KMH * 59.0 for d in row] for row in self.dist.tolist()]", "Fahrzeit-Umrechnung"),
]


def run_mutant(idx, mutant, workdir):
    fname, old, new, desc = mutant[:4]
    nth = mutant[4] if len(mutant) > 4 else None
    work = Path(workdir) / f"m{idx}"
    shutil.copytree(ROOT, work, ignore=shutil.ignore_patterns("__pycache__", ".git", "data", "venv", ".pytest_cache", "tools"))
    p = work / fname
    text = p.read_text(encoding="utf-8")
    if nth is None and text.count(old) != 1:
        return idx, desc, f"FEHLER: Stelle kommt {text.count(old)}-mal vor"
    if nth is None:
        text = text.replace(old, new)
    else:
        parts = text.split(old)
        if nth >= len(parts) - 1:
            return idx, desc, "FEHLER: Stelle zu selten"
        text = old.join(parts[:nth + 1]) + new + old.join(parts[nth + 1:])
    p.write_text(text, encoding="utf-8")
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    r = subprocess.run([sys.executable, "-B", "-m", "pytest", "-x", "-q", "-p", "no:cacheprovider", *TESTS], cwd=work, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace")
    shutil.rmtree(work, ignore_errors=True)
    return idx, desc, "gefunden" if r.returncode != 0 else "ÜBERLEBT"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--only", default="")
    a = ap.parse_args()
    todo = [(i, m) for i, m in enumerate(MUTANTS) if a.only in m[0] or a.only in m[3]]
    with tempfile.TemporaryDirectory() as tmp, ThreadPoolExecutor(max_workers=a.jobs) as ex:
        results = list(ex.map(lambda im: run_mutant(im[0], im[1], tmp), todo))
    bad = 0
    for idx, desc, res in sorted(results):
        print(f"{idx:2d} {res:10s} {MUTANTS[idx][0]}: {desc}")
        bad += res != "gefunden"
    print(f"\n{len(results) - bad}/{len(results)} Mutanten gefunden")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
