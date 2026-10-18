"""Zufalls-Seeds für die Presets suchen: der erste Zufalls-Seed ab 500 (außerhalb der Stichprobe 1 bis 30 der Messreihe), auf dem die Geschichte des Presets
nach den Kriterien aus ruf_stories.py stimmt. Aufruf: python tools/preset_search.py [--max 300] ; Ausgabe: PRESETS-Einträge zum Einfügen in ruf_constants.py."""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import ruf_constants as C  # noqa: E402
import ruf_evaluation as ev  # noqa: E402
import ruf_stories as ST  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max", type=int, default=300)
    ap.add_argument("--start", type=int, default=500)
    a = ap.parse_args()
    found = {}
    for name, preset in C.PRESETS.items():
        for seed in range(a.start, a.start + a.max):
            s = ST.settings_of(preset, seed)
            an = ev.analyse(s)
            ref = ev.analyse(ST.reference_settings(s)) if name in ST.NEEDS_REFERENCE else None
            if an.K != float("inf") and ST.check(name, an, ref):
                found[name] = seed
                r = an.ratio
                print(f"{name}: Zufalls-Seed {seed} (Verhältnis {'-' if r is None else round(r, 2)}, K {an.K}, N {an.N})", flush=True)
                break
        else:
            print(f"{name}: kein Zufalls-Seed in {a.max} Versuchen", flush=True)
    print("\nPRESETS = {")
    for name, preset in C.PRESETS.items():
        d = dict(preset)
        d["seed"] = found.get(name, d["seed"])
        print(f"    {name!r}: {d!r},")
    print("}")


if __name__ == "__main__":
    main()
