# Rufbus oder Linienbus: wo kippt es? – Streamlit-Demo

<!-- TODO nach dem Deploy: direkt hierher den Live-Link setzen (Leerzeile davor und danach):
**[→ Demo live ausprobieren](https://sebastianhanisch-rufbus-demo.streamlit.app/)** -->

Fall-Demo für die Website „Sebastian Hanisch – Operations Research und Machine Learning“ (`demos.html`, Gruppe ÖPNV), zweite Demo der Seite [ÖPNV und Fernverkehr optimieren](https://sebastianhanisch.net/oepnv-fernverkehr-optimierung.html) nach dem festen Liniennetz ([transit-demo](https://github.com/sebastian-hanisch/transit-demo)). Ein **Linienbus** fährt, ob jemand einsteigt oder nicht; ein **Rufbus** (Dial-a-Ride) fährt nur, wenn jemand ihn ruft. Die Demo rechnet live ein Szenario (Gebiet, Haltepunkte, Fahrtwünsche) und stellt daneben eine **vorgerechnete Messreihe über 30 Zufalls-Seeds je Zelle**: zwei Kostenkurven, den Kipppunkt mit Band, den Einfluss von Wartezeit, Umweg, Plätzen, Gebiet und Qualitätsmaß, drei Rufbus-Verfahren und einen exakten Tab für kleine Instanzen.

## Warum dieses Problem

Ab wie vielen Fahrtwünschen pro Stunde lohnt sich ein Rufbus gegen einen Linienbus, und warum hängt die Antwort daran, was man unter **gleicher Qualität** versteht? Der Rufbus braucht nur so viele Fahrzeuge, wie die Nachfrage verlangt; der Linienbus braucht für dieselbe Wartezeit praktisch immer dieselbe Flotte. Bei gleicher mittlerer Wartezeit kippt es deshalb bei rund 44 Anfragen pro Stunde im 10 × 10-km-Gebiet. Fordert man stattdessen gleiche mittlere Gesamtreisezeit höchstens 30 Minuten, gibt es keinen Kipppunkt: Der Rufbus ist überall billiger.

## Modell

- **Szenario:** quadratisches Gebiet (6, 10 oder 16 km Kantenlänge) mit 20, 30 oder 40 Haltepunkten, Luftlinie bei 30 km/h, 0,5 min Halt je Aufnahme oder Absetzen. Die Nachfrage zwischen den Haltepunkten ist ungleich verteilt (ein Teil konzentriert sich auf zwei Zentren). Fahrtwünsche kommen über einen Betriebstag von 6 Stunden; **gemessen wird zwischen Minute 45 und 315**, weil das System leer startet.
- **Rufbus:** sofortige Zusage oder Absage; Abholung höchstens W Minuten nach der Anfrage (10, 15 oder 25), Fahrzeit höchstens Umwegfaktor (1,5 oder 2,0) mal Direktfahrt plus 2 Minuten, Platzgrenze. Verfahren: sofortige Einfügung (billigste zulässige Position), Einfügen + Verbessern (Umlegen und Austauschen) und Batch (Fenster 5 Minuten). **Flotte K\***: die kleinste Flottengröße, ab der mindestens 90 % der Fahrtwünsche angenommen werden.
- **Linienbus:** sieben feste Linienentwürfe (eine Linie über alle Haltepunkte, Sternnetze mit 1 bis 4 Linien, zwei Teilabdeckungen mit Fußweg), Fahrzeuge gleichmäßig verteilt, periodischer Fahrplan mit Zufallsphase, Wegewahl nach erwarteter Zeit. **N\***: die kleinste Fahrzeugzahl, die dasselbe Qualitätsmaß erreicht wie der Rufbus.
- **Kosten:** Fahrzeugstunden je bedientem Fahrgast (Flotte mal Messfenster von 4,5 Stunden), keine Euro-Kosten, weil keine Kostensätze erfunden werden sollen. Der **Kipppunkt** ist die Dichte, bei der beide Kurven gleich sind (log-linear zwischen den gemessenen Dichten interpoliert, Bootstrap über die Zufalls-Seeds).
- Die Formeln stehen im Expander „📐 Mathematische Formulierung“ der App.

## Methodik

- **Live:** ein Szenario mit den Reglern der Seitenleiste: Flottensuche K\* für den Rufbus (Flottengröße von unten hochzählen, bis der Servicegrad dreimal in Folge mindestens 95 % ist), N\* für jeden der sieben Linienentwürfe, Kosten, Reisezeiten, Karte. Eine Meldung in drei Zuständen (Rufbus billiger, Linienbus billiger, etwa gleich teuer) nennt immer auch den Reisezeit-Unterschied und ordnet das Szenario in das P10-bis-P90-Band der Messreihe ein, sofern die Einstellung der Basiszelle entspricht.
- **Messreihe (vorgerechnet, nie live):** 202 Zellen mit je 30 Zufalls-Seeds (60 051 Rufbus-Läufe, 14 700 Linienbus-Zeilen, 930 exakte Kleininstanzen), erzeugt mit `tools/sweep_ruf.py`, `sweep_line.py`, `sweep_exact.py`, ausgewertet mit `tools/analyse.py` und als `data/ruf_results.json` (unter 150 kB) abgelegt. Die Rohdaten (rund 190 MB) liegen nicht im Repo; die Werkzeuge schreiben sie in den Ordner aus `RUF_RAW_DIR` (Standard: `../oepnv-planung/messreihe_rufbus_ap0`). Alle Zufallsquellen sind ganzzahlig (SplitMix64, Raster 5 bis 95): Szenarien und Suchläufe sind auf jeder Plattform und mit jeder numpy-Version gleich.
- **Vorab-Reihe und Neumessung:** Die erste Messreihe lief mit numpy-Zufall; für den Bau wurde alles auf dem ganzzahligen Generator neu gemessen (siehe „Befunde und Korrekturen gegenüber dem Plan“).
- **Exakt-Tab:** Aufzählung aller Reihenfolgen je Fahrzeug mit freiem Abwarten, für ein Los von 4 bis 8 gleichzeitig bekannten Anfragen und 1 bis 3 Fahrzeuge.

## Befunde (gemessen, keine Behauptungen)

Alle Zahlen stehen in `data/ruf_results.json` und sind in `tests/test_claims.py` nachgerechnet.

| Frage | Befund |
|---|---|
| Wächst die Rufbus-Flotte mit der Nachfrage? | **Langsamer als diese:** K\* steigt von 2,6 Fahrzeugen bei 3 Anfragen/h auf 14,3 bei 100 Anfragen/h, Anpassung K\* ∝ λ^0,49; die Fahrzeugstunden je Fahrgast fallen von 0,85 auf 0,15 (Faktor 5,5). |
| Wo kippt es bei gleicher mittlerer Wartezeit? | **0,44 Anfragen je km² und Stunde, 44 je Stunde** im 10 × 10-km-Gebiet (Bootstrap 0,42 bis 0,46), mit dem besten Linienentwurf je Szenario. Mit einer einzigen Linie über alle Haltepunkte: 0,65; mit Teilabdeckung (Fußweg 1,0 km): 0,54; mit Sternnetzen: kein Kipppunkt. |
| Hängt der Kipppunkt am Qualitätsmaß? | **Ja.** Gleiche mittlere Gesamtreisezeit höchstens 30 min (und 25 min): kein Kipppunkt. Höchstens 35 min: kein Kipppunkt im Mittel, in 53 % der Bootstrap-Resamples keiner. Höchstens 40 min: 0,52; höchstens 45 min: 0,25. |
| Was zahlt der Linienbus-Fahrgast bei gleicher Wartezeit? | Bei Dichte 0,4 wartet er im Mittel 7,9 min (Rufbus 8,4), sitzt aber 31,9 min im Fahrzeug (Rufbus 12,6): Gesamtzeit 39,8 min gegen 21,0 min (Linienbus mit einer Linie über alle Haltepunkte). |
| Trägt der Kipppunkt über das Gebiet? | In Anfragen je Stunde ja: 44 im 10 × 10-km-Gebiet, 48 im 16 × 16-km-Gebiet, im 6 × 6-km-Gebiet bis 36 Anfragen/h keiner. Nicht über die höchste Wartezeit: 61 Anfragen/h bei 10 min, 28 bei 25 min. |
| Schlägt Batch die sofortige Einfügung? | **Nein.** Batch (Fenster 5 min, mit Verbessern) braucht 0,3 bis 1,3 Fahrzeuge mehr, Fenster 10 min 2,8 bis 3,9 mehr; das Warten auf den Stapel verbraucht das Wartezeitbudget. Einfügen + Verbessern spart bei Dichte 0,8 und 1,0 nur 0,47 und 0,60 Fahrzeuge, bei geringerer Dichte höchstens 0,27. |
| Helfen mehr Plätze? | **8 statt 4 Plätze ändern die Flotte praktisch nicht** (bei Dichte 1,0: −0,20 ± 0,10 Fahrzeuge). Der Umwegfaktor wirkt stärker (2,0 statt 1,5: −0,93 ± 0,10); ein Platz statt vier kostet +7,2 Fahrzeuge. |
| Wie stark bündelt der Rufbus? | Der Anteil der Fahrgäste mit Mitfahrern steigt von 17 % (Dichte 0,03) auf 91 % (Dichte 1,0); gegenüber Einzelfahrten spart das bei Dichte 1,0 rund 33 % der Flotte. |
| Wie weit liegen die Heuristiken vom Optimum? | Im Los von 8 Anfragen und 1 Fahrzeug (Wartezeit 15 min) bedient die sofortige Einfügung 78 % der Anfragen des Exakten, Batch 87 %; auf Flottenebene schrumpft der Abstand auf 0 bis wenige Prozent. Keine Heuristik schlägt den Exakten (0 von 930 Vergleichen). |
| Wie lange rechnet ein Live-Szenario? | Meist unter einer Sekunde; bei hoher Dichte mit „Einfügen + Verbessern“ einige Sekunden (Spinner und Ergebnis-Cache je Einstellung). |

## Ehrliche Grenzen

- **Der Kipppunkt ist keine Eigenschaft der beiden Betriebsformen**, sondern des gewählten Qualitätsmaßes und der Linienführung. Wer „ab x Anfragen je km²“ behauptet, trifft nur für ein Gebiet und ein Maß zu.
- **Der „faire“ Linienbus ist nicht eindeutig.** Der Hauptwert wählt je Szenario den besten von sieben Entwürfen mit Kenntnis der gezogenen Anfragen; das ist leicht günstig für den Linienbus. Teilabdeckungs-Entwürfe bedienen nur Haltepunkte im Fußweg-Einzugsbereich, der Fußweg steckt in der Gesamtzeit, nicht in der Wartezeit.
- **Der Rufbus ist optimistisch modelliert:** keine Leerfahrten-Neupositionierung, keine Vorbestellung, keine Fahrerpausen, keine gemischte Flotte, keine Spitzen im Tagesverlauf, virtuelle Haltepunkte ohne Fußweg.
- **Kosten sind Flottenstunden der ganzen Betriebsdauer.** Rechnet man nur gefahrene Stunden, rückt der Kipppunkt auf 0,54.
- **Ein Szenario streut** von Zufalls-Seed zu Zufalls-Seed; die Messreihe steht deshalb gleichberechtigt daneben. Die Messreihe gilt für die Basiseinstellung (FCFS, 4 Plätze, Umweg 1,5, Wartezeit 15 min, 10 × 10 km, 30 Haltepunkte, mittlere Konzentration) und die vorgerechneten Einzelabweichungen davon.
- Nur 30 Zufalls-Seeds je Zelle: Bänder und Standardfehler stehen überall dabei; bei Reisezeit ≤ 35 min liegt der Kipppunkt genau an der Auflösungsgrenze der Reihe.
- Das Exakte (Aufzählung) ist ein Lehrstück für kleine Instanzen, keine Betriebsaussage.

## Verifikation

- **Kern:** Einfügeheuristik gegen vollständige Aufzählung auf 150 Zufallszuständen (Menge der zulässigen Positionen und Kosten); ganze Läufe aller drei Verfahren gegen einen unabhängigen Prüfer aus den Ausführungsprotokollen (Fahrzeit, Kapazität, Wartezeit, Umweg, Reihenfolge, Zielort, Kostenbuchführung); exakte Aufzählung gegen Permutationsaufzählung; Mini-Instanz von Hand gerechnet (`tests/test_sim.py`).
- **Linienbus:** Zeiten einer Linie von Hand, Winkelreihenfolge gegen `atan2`, Wegetabelle gegen networkx (`tests/test_line.py`).
- **Zufallsquelle:** SplitMix64 gegen die veröffentlichten Referenzwerte, eingefrorene Referenzwerte für drei Szenarien (`tests/test_rng.py`, `tests/test_network.py`).
- **Live gegen Messreihe:** K\* und N\* eines Live-Szenarios sind für denselben Zufalls-Seed **bitgleich** zur Messreihe (`tests/test_results.py`).
- **Mutationsprüfung:** `tools/mutation_check.py` ändert 36 Rechenstellen einzeln (Grenzen, Kosten, Abbruchregeln, Takt, Wegewahl, Zufallsrate); alle 36 werden von mindestens einem Test gefunden. Bewusst nicht in der Liste: Änderungen, die gleichwertig sind oder nur eine Heuristik-Vorliebe betreffen (Umweggrenze beim Einfügen ans Routenende greift nie, Umlegen ohne Ersparnis, Überschneidungsprüfung der exakten Aufteilung, Bedauern im Batch).
- **Presets:** jede Geschichte stimmt auf dem gezeigten Szenario (`tests/test_stories.py`), jede Schwelle kippt einzeln an künstlichen Werten.
- **Oberfläche:** AppTest-Rauchtest (jeder Button, jeder Regler am Minimum und Maximum), Layout (Schnellstart oben, fester Kopf, aktives Preset hervorgehoben), Footer.

## Dateistruktur

| Datei | Zweck |
|---|---|
| `.github/workflows/tests.yml` | CI: Push, Pull Request, wöchentlicher Canary |
| `.gitignore` | venv, Caches, Streamlit-Secrets |
| `.streamlit/config.toml` | Streamlit-Einstellungen (keine Nutzungsstatistik) |
| `app.py` | Streamlit-App |
| `data/ruf_results.json`, `data/README_data.md` | vorgerechnete Messreihe und Beschreibung ihrer Schlüssel |
| `requirements-dev.txt` | Laufzeit plus pytest und networkx |
| `requirements.txt` | Laufzeit-Bibliotheken (ungepinnt) |
| `ruf_constants.py` | Modellannahmen, Reglerstufen, Farben, Presets |
| `ruf_evaluation.py` | Live-Szenario: Einstellungen, K\*, N\*, Kosten, Verdikt |
| `ruf_exact.py` | exakte Aufzählung, Offline-Heuristik |
| `ruf_layout.py` | Fester Kopf (Stylesheet) |
| `ruf_line.py` | Linienentwürfe, Fahrplan, Wegetabelle, Auswertung |
| `ruf_network.py` | ganzzahliger Haltepunkt-, Nachfrage- und Anfragengenerator |
| `ruf_pdf_export.py` | Szenario-Bericht als PDF |
| `ruf_presets.py` | Permalink (Begrenzen), Presets, Zufalls-Seed-Button |
| `ruf_results.py` | Laden und Abfragen der vorgerechneten Messreihe |
| `ruf_rng.py` | SplitMix64 |
| `ruf_search.py` | Flottensuche K\*, N\*, Kosten, Kipppunkt |
| `ruf_sim.py` | Einfügeheuristik, Online-Simulation, Auswertung, Prüfer |
| `ruf_stories.py` | Abnahmekriterien der Presets |
| `ruf_visualization.py` | Plotly-Abbildungen (Achsen gesperrt) |
| `tools/` | Sweeps, Analyse, Ergebnisdatei, Preset-Suche, Mutationsprüfung |
| `tests/` | Mini-Instanz, Orakel, Zufallsquelle, Linienbus, Suche, Ergebnisse, Presets, Layout, Smoke-Test, Footer |

## Bewusst nicht umgesetzt

- Leerfahrten-Neupositionierung, Vorbestellung, Fahrerpausen, gemischte Flotten, Nachfrageprofil über den Tag, Haustür-Haltepunkte, Fußwege beim Rufbus.
- Mischformen (Rufbus als Zubringer zur Linie), nachfrageorientierte Linienführung, nutzenbasierte Wahl (Logit) der Fahrgäste.
- Euro-Kosten (keine erfundenen Kostensätze), Animation der Fahrzeuge (nur ein Standbild je Uhrzeit).
- Batch-Fenster unter 2 Minuten, adaptive Fenster, Ejection Chains.
- Ein Regler für Zeitwert oder Geschwindigkeit: sie skalieren nur alle Zeiten.

## Befunde und Korrekturen gegenüber dem Plan

- **Neumessung auf dem ganzzahligen Generator (AP 0):** Von 322 verglichenen Kennzahlen der Vorab-Reihe bestehen 269, 51 sind verschoben, 2 brechen. Der Kipppunkt der Basis liegt neu bei 0,44 (Vorab 0,42), fast alle Varianten 0,02 bis 0,06 höher; K\* ist bei mittleren Dichten 0,3 bis 0,4 Fahrzeuge höher. Kein Vorzeichen eines Verfahrenseffekts dreht sich.
- **Gebrochen:** Bei gleicher Reisezeit ≤ 35 min hatte die Vorab-Reihe den Kipppunkt 1,00 (in 42 % der Resamples keiner); neu gibt es keinen (53 % der Resamples ohne). Die Aussage „praktisch nie“ wird bestätigt, der Zahlenwert 1,00 ist nicht reproduzierbar.
- **Meldung:** statt eines Zustands „im Normalbereich“ gibt es drei Zustände nach dem Kostenverhältnis (Rufbus billiger, Linienbus billiger, etwa gleich teuer); die Einordnung in das Band der Messreihe steht als zusätzlicher Satz.
- **Kostenkurven:** Das Band über die Zufalls-Seeds gibt es nur für den Rufbus der Basiszelle; für den Linienbus stehen Mittelwerte.
- **Presets:** Zufalls-Seeds ab 500 (außerhalb der Stichprobe 1 bis 30), das erste Preset „Am Kipppunkt“ ist die Voreinstellung.
- **Plätze-Regler:** Stufen 1, 2, 4 und 8; die Stufen 4 und 8 unterscheiden sich praktisch nicht, das steht als Befund im Text statt zwei unwirksame Stufen zu verstecken.

## Verwandte Demos mit demselben mathematischen Modell

- **[transit-demo](https://github.com/sebastian-hanisch/transit-demo):** das feste Liniennetz, aus dem der Linienbus-Vergleich hervorgeht; dort wird nur die Linienführung gewählt, keine Flotte.
- **[taktfahrplan-demo](https://github.com/sebastian-hanisch/taktfahrplan-demo):** Abfahrtsminuten für feste Linien, die nächste Stufe nach dem Liniennetz.
- **[vrp_demo](https://github.com/sebastian-hanisch/vrp_demo):** Touren mit Zeitfenstern; Pickup and Delivery steht dort nur als ungebaute Erweiterung. Der Rufbus ist ein Dial-a-Ride-Problem (Pickup and Delivery mit Zeitfenstern und Fahrzeitlimit).
- **[nahverkehr-demo](https://github.com/sebastian-hanisch/nahverkehr-demo):** Same-Day-Aufträge und Planstabilität; andere Frage (Annahme und Neuplanung von Touren, keine Fahrgäste).
- **[warehouse-transfer-demo](https://github.com/sebastian-hanisch/warehouse-transfer-demo):** Pickup and Delivery im Lager mit Umschlagpunkten; gleiche Struktur der Einfügung, andere Kulisse.

## Lokal ausführen

```bash
python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate

pip install -r requirements.txt
streamlit run app.py
```

## Tests ausführen

```bash
pip install -r requirements-dev.txt
pytest tests/ -v
```

Gebaut mit Streamlit, Plotly und NumPy.

---

Diese Demo ist Teil des Portfolios von [Sebastian Hanisch](https://sebastianhanisch.net) – Operations Research und Machine Learning ([Über mich](https://sebastianhanisch.net/ueber-mich.html)). Mehr zum Thema: [ÖPNV und Fernverkehr optimieren](https://sebastianhanisch.net/oepnv-fernverkehr-optimierung.html).
