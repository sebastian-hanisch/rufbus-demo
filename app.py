"""Rufbus oder Linienbus: wo kippt es? - interaktive Fall-Demo
Sebastian Hanisch - Operations Research und Machine Learning

Ein Rufbus (Dial-a-Ride) fährt nur, wenn jemand ihn ruft; ein Linienbus fährt immer. Ab wie vielen Fahrtwünschen pro Stunde lohnt sich der
Rufbus, und warum hängt die Antwort daran, was man unter gleicher Qualität versteht? Live ein Szenario, daneben die vorgerechnete Messreihe.

Lauffähig mit: streamlit run app.py
"""

import math

import pandas as pd
import streamlit as st

import ruf_constants as C
import ruf_evaluation as ev
import ruf_results as R
import ruf_search as S
from ruf_evaluation import Settings
from ruf_layout import dunkles_design, kopf_css
from ruf_network import World
from ruf_pdf_export import build_report
from ruf_presets import (
    SETTING_SPECS,
    allowed_lams,
    fix_state,
    init_session_state_defaults,
    load_permalink_settings,
    randomize_seed,
    sidebar_presets,
    sync_query_params,
)
from ruf_rng import SplitMix64
from ruf_sim import INF, Sim, summarize
from ruf_exact import exact_solve_flex, offline_heuristic
from ruf_visualization import build_cost_curves, build_map, build_pooling, build_proc, build_scaling

st.set_page_config(page_title="Rufbus oder Linienbus – Sebastian Hanisch", layout="wide")


def de(x, digits=1):
    """Zahl mit Dezimalkomma; nur die Zahl wird umformatiert, nie ein ganzer Satz (Tausenderpunkt-Falle)."""
    return f"{x:.{digits}f}".replace(".", ",")


@st.cache_resource(show_spinner=False, max_entries=12)
def _world(area, stops, hub, seed):
    return World(seed, float(area), stops, hub)


@st.cache_resource(show_spinner=False, max_entries=40)
def _line_res(area, stops, hub, seed, lam, design):
    w = _world(area, stops, hub, seed)
    return S.line_summaries(w, design, w.requests(float(lam)), seed)


@st.cache_resource(show_spinner=False, max_entries=24)
def _analysis(s: Settings):
    return ev.analyse(s, line_res_for=lambda d: _line_res(s.area, s.stops, s.hub, s.seed, s.lam, d))


# Fester Kopf: nur der Titel bleibt beim Scrollen oben (Stylesheet in ruf_layout.py).
st.html(kopf_css(dunkles_design()))
with st.container(key="kopf"):
    st.title("🚐 Rufbus oder Linienbus: wo kippt es?")
st.markdown(
    """
Ein **Linienbus** fährt, ob jemand einsteigt oder nicht; ein **Rufbus** fährt nur, wenn jemand ihn ruft. Ab wie vielen Fahrtwünschen pro Stunde sich das lohnt, ist eine **Messfrage**,
und die Antwort hängt daran, **was man als gleiche Qualität ansieht**. Die Demo rechnet live ein Szenario (Gebiet, Haltepunkte, Fahrtwünsche) und zeigt daneben die **vorgerechnete Messreihe**
über 30 Zufalls-Seeds je Zelle: zwei Kostenkurven, den Kipppunkt mit Band und den Einfluss von Wartezeit, Umweg, Plätzen und Qualitätsmaß.

Weiter unten: **📐 Wo kippt es?**, **📈 Skalenerträge und Bündeln** und der Expander **🔧 Wie wir das erreichen – vollständiger Methodenvergleich**.
Vorgänger und Nachbarn: das feste Liniennetz der [ÖPNV-Liniennetz-Demo](https://sebastianhanisch-transit-demo.streamlit.app/) und die Abfahrtsminuten im [Taktfahrplan](https://sebastianhanisch-taktfahrplan-demo.streamlit.app/).
"""
)

# erklaerseite:einfach:start (erzeugt von tools/set_demo_explainer.py (Website-Repo) aus tools/content/explainers/rufbus-oder-linienbus-erklaert.json, nicht von Hand ändern)
with st.expander("💬 In einfachen Worten"):
    st.markdown(
        """
Ein **Linienbus** fährt nach festem Plan, ob jemand einsteigt oder nicht. Ein **Rufbus** fährt nur, wenn jemand ihn ruft, und nimmt auf einer Tour oft mehrere Fahrgäste zusammen mit. Bei wenigen Fahrtwünschen braucht der Rufbus wenige Fahrzeuge und ist billiger. Der Linienbus braucht dagegen für dieselbe Wartezeit praktisch immer dieselbe Flotte, egal wie viele Fahrgäste kommen. Die Demo sucht den **Kipppunkt**, ab dem der Linienbus billiger wird, und zeigt, dass er davon abhängt, was man als gleiche Qualität ansieht: gleiche Wartezeit oder gleiche Gesamtreisezeit. Je nach Maß gibt es einen Kipppunkt oder keinen. Es ist ein stark vereinfachtes Modell, das den Vergleich erklärt, keinen allgemeingültigen Schwellenwert.

[Ausführlich und verständlich erklärt, mit Fachteil](https://sebastianhanisch.net/rufbus-oder-linienbus-erklaert.html)
        """
    )
# erklaerseite:einfach:end

st.caption("🔗 Die Adresszeile oben spiegelt Ihre aktuelle Konfiguration wider – einfach kopieren, um ein Szenario zu teilen.")

load_permalink_settings()
init_session_state_defaults()
fix_state()

with st.sidebar:
    sidebar_presets()  # Schnellstart oben, das aktive Preset ist hervorgehoben
    st.header("⚙️ Einstellungen")
    st.markdown("**Gebiet und Nachfrage**")
    area = st.selectbox("Gebiet (Kantenlänge)", C.AREA_STEPS, key="area_select", format_func=lambda v: f"{v} × {v} km",
                        help="Quadratisches Bediengebiet. Bei gleicher Stundenzahl ändert das die Dichte; in Anfragen je Stunde bleibt der Kipppunkt über die Gebietsgröße ähnlich.")
    lam = st.select_slider("Anfragen je Stunde", options=allowed_lams(area), key="lam_select",
                           help="Fahrtwünsche pro Stunde im ganzen Gebiet (gemessene Stufen). Im 6 × 6-km-Gebiet nur bis 36, weil die Messreihe bis zur Dichte 1,0 je km² reicht.")
    stops = st.selectbox("Haltepunkte", C.STOP_STEPS, key="stops_select", help="So viele mögliche Ein- und Ausstiegsorte; sie bestimmen Linienentwürfe und Anfragenverteilung.")
    hub = st.selectbox("Nachfragekonzentration", C.HUB_STEPS, key="hub_select",
                       format_func=lambda v: {0: "gleichverteilt", 50: "mittel (Voreinstellung)", 100: "stark auf zwei Zentren"}[v],
                       help="Wie stark die Nachfrage auf zwei Haltepunkte (Zentren) konzentriert ist.")
    st.markdown("**Rufbus**")
    wait = st.selectbox("Höchste Wartezeit bis zur Abholung", C.WAIT_STEPS, key="wait_select", format_func=lambda v: f"{v} min",
                        help="Das Versprechen des Rufbusses: Abholung höchstens so lange nach der Anfrage. Stärkster Einfluss auf den Kipppunkt.")
    detour = st.selectbox("Umwegfaktor", C.DETOUR_STEPS, key="detour_select", format_func=lambda v: de(v),
                          help="Fahrzeit höchstens Faktor mal Direktfahrt plus 2 Minuten. Wirkt auf die Flotte stärker als zusätzliche Plätze.")
    cap = st.selectbox("Plätze je Fahrzeug", C.CAP_STEPS, key="cap_select",
                       help="Bei 1 gibt es keine Bündelung, bei 2 wenig. Von 4 auf 8 ändert sich die Flotte praktisch nicht (Befund der Messreihe).")
    proc = st.selectbox("Verfahren", ev.PROC_OPTIONS, key="proc_select", format_func=lambda v: ev.PROC_LABEL[v],
                        help="Wie Fahrtwünsche den Fahrzeugen zugeteilt werden. Warten auf einen Stapel kostet Wartezeitbudget.")
    st.markdown("**Vergleich mit dem Linienbus**")
    measure = st.selectbox("Qualitätsmaß (gleich bei beiden)", ev.MEASURE_OPTIONS, key="measure_select", format_func=lambda v: ev.MEASURE_LABEL[v],
                           help="Was „gleich gut“ heißt: gleiche mittlere Wartezeit, oder beide Formen halten eine mittlere Gesamtreisezeit ein. Der Kipppunkt hängt an dieser Wahl.")
    design = st.selectbox("Linienführung des Linienbusses", ev.DESIGN_OPTIONS, key="design_select", format_func=lambda v: ev.DESIGN_LABEL[v],
                          help="Welcher Linienentwurf verglichen wird. „Bester Entwurf“ wählt je Szenario den günstigsten von sieben; das ist leicht günstig für den Linienbus.")
    seed = st.number_input("Zufalls-Seed des Szenarios", *(SETTING_SPECS["seed_input"].lo, SETTING_SPECS["seed_input"].hi), key="seed_input", step=1)
    st.button("🎲 Neues Szenario generieren", width="stretch", on_click=randomize_seed)

sync_query_params({k: st.session_state[k] for k in SETTING_SPECS})

settings = Settings(lam=int(lam), area=int(area), stops=int(stops), wait=float(wait), detour=float(detour), cap=int(cap), hub=int(hub), proc=proc, measure=measure,
                    design=design, seed=int(seed))

with st.spinner("Rechne Rufbus und Linienbus für dieses Szenario …"):
    a = _analysis(settings)
world = a.world

with st.expander("📍 Haltepunkte (nicht editierbar – die Nachfrage hängt an der Erzeugung des Szenarios)"):
    dem = world.demand.sum(axis=1)
    st.dataframe(pd.DataFrame({"Haltepunkt": [f"H{i + 1}" for i in range(world.n)], "x (km)": [round(float(c[0]), 2) for c in world.coords],
                               "y (km)": [round(float(c[1]), 2) for c in world.coords], "Nachfragegewicht": [int(v) for v in dem]}), width="stretch", hide_index=True)

# --- Ihr Szenario --------------------------------------------------------------------------------------------------------------------------

st.markdown("## 🎯 Ihr Szenario")
dens_now = settings.density
st.caption(f"{settings.lam} Anfragen je Stunde auf {settings.area} × {settings.area} km: Dichte {de(dens_now, 2)} je km² und Stunde. "
           f"In diesem Szenario kommen im Messfenster ({int(C.T0_MEAS)} bis {int(C.T1_MEAS)} Minuten) {int(a.ruf.get('n_req', 0))} Anfragen.")

if a.ruf == {} or a.K == INF:
    st.warning("Mit dieser Einstellung erreicht der Rufbus den Servicegrad von 90 % auch bei 80 Fahrzeugen nicht (Wartezeit oder Umweg zu streng für die Nachfrage).")
    st.stop()

linie_total = a.line.get("total") if a.line else None
m1, m2 = st.columns(2)
m1.metric("Fahrzeuge Rufbus", f"{a.K:.0f}", delta=(f"{a.K - a.N:+.0f} gegen Linienbus" if a.N != INF else "Linienbus nicht erreichbar"), delta_color="inverse",
          help="Kleinste Flotte, die mindestens 90 % der Fahrtwünsche annimmt (und alle größeren Flotten ebenso).")
m2.metric("Fahrzeuge Linienbus", f"{a.N:.0f}" if a.N != INF else "nicht erreichbar", delta=(f"{a.N - a.K:+.0f} gegen Rufbus" if a.N != INF else None), delta_color="inverse",
          help=f"Kleinste Fahrzeugzahl des Entwurfs „{ev.DESIGN_LABEL[a.design]}“ bei Maß „{ev.MEASURE_LABEL[settings.measure]}“.")
m3, m4 = st.columns(2)
m3.metric("Fahrzeugstunden je Fahrgast (Rufbus)", de(a.ruf_cost, 3),
          delta=(f"{100 * (a.ratio - 1):+.0f} % gegen Linienbus ({de(a.line_cost, 3)})" if a.ratio is not None else None), delta_color="inverse",
          help="Flotte mal Messfenster (4,5 Stunden) geteilt durch die bedienten Fahrgäste.")
m4.metric("Mittlere Reisezeit Rufbus", f"{de(a.ruf['total'])} min", delta=(f"{a.ruf['total'] - linie_total:+.1f} min gegen Linienbus ({de(linie_total)} min)".replace(".", ",") if linie_total is not None else None),
          delta_color="inverse", help="Wartezeit plus Fahrzeit der angenommenen Fahrgäste.")

dev = []
if settings.area != 10:
    dev.append("Gebiet")
if settings.stops != 30:
    dev.append("Haltepunkte")
if settings.wait != 15.0:
    dev.append("Wartezeit")
if settings.detour != 1.5:
    dev.append("Umwegfaktor")
if settings.cap != 4:
    dev.append("Plätze")
if settings.hub != 50:
    dev.append("Nachfragekonzentration")
if settings.proc != "fcfs":
    dev.append("Verfahren")
band = None if dev else R.band_for(settings.measure, settings.design, dens_now)

verdict = a.verdict
line_txt = (f"{de(linie_total)} min" if linie_total is not None else "-")
common = (f" Bei gleichem Maß („{ev.MEASURE_LABEL[settings.measure]}“) braucht der Rufbus {a.K:.0f} Fahrzeuge, der Linienbus ({ev.DESIGN_LABEL[a.design]}) "
          + (f"{a.N:.0f}" if a.N != INF else "mehr als 30") + f". Der Fahrgast sitzt im Rufbus im Mittel {de(a.ruf['total'])} min unterwegs, im Linienbus {line_txt}.")
if verdict == "ruf":
    verdict_text = f"Der Rufbus ist bei diesen Annahmen **billiger**: {de(a.ruf_cost, 3)} gegen {de(a.line_cost, 3) if a.line_cost != INF else 'nicht erreichbar'} Fahrzeugstunden je Fahrgast." + common
    st.success(verdict_text)
elif verdict == "line":
    verdict_text = f"Der Linienbus ist bei diesen Annahmen **billiger**: {de(a.line_cost, 3)} gegen {de(a.ruf_cost, 3)} Fahrzeugstunden je Fahrgast." + common
    st.info(verdict_text)
elif verdict == "gleich":
    verdict_text = f"Etwa **gleich teuer** (Verhältnis Rufbus zu Linienbus {de(a.ratio, 2)}): Sie liegen nahe am Kipppunkt." + common
    st.info(verdict_text)
else:
    verdict_text = "Keine der beiden Formen erreicht mit dieser Einstellung die geforderte Qualität."
    st.warning(verdict_text)
if band is not None:
    p10, med, p90 = band
    inside = p10 <= a.ratio <= p90 if a.ratio is not None else False
    st.caption(f"Messreihe (30 Zufalls-Seeds, gleiche Einstellung und Maß): Kostenverhältnis Rufbus zu Linienbus bei dieser Dichte im Median {de(med, 2)} (P10 bis P90: {de(p10, 2)} bis {de(p90, 2)}); "
               f"dieses Szenario liegt {'im' if inside else 'außerhalb des'} Normalbereich{'' if inside else 's'}. Der Kipppunkt der Messreihe liegt bei {R.lam_text(R.variants()[0])} Anfragen je Stunde.")
elif dev:
    st.caption("Die vorgerechnete Messreihe gilt für die Basiseinstellung (10 × 10 km, 30 Haltepunkte, 15 min, Umweg 1,5, 4 Plätze, mittlere Konzentration, sofortige Einfügung); "
               f"Ihre Einstellung weicht ab: {', '.join(dev)}. Passende Varianten stehen im Abschnitt „Wo kippt es?“.")

tmin = st.slider("Uhrzeit auf der Karte (Minuten nach Betriebsbeginn)", int(C.T0_MEAS), int(C.T1_MEAS), 180, step=15, key="time_slider",
                 help="Zeigt die Wege der Rufbus-Fahrzeuge im Zeitfenster von 20 Minuten um diese Uhrzeit.")
st.plotly_chart(build_map(a, float(tmin)), width="stretch", key=f"map_{tmin}")
st.caption("Punkte: Haltepunkte (Größe = Nachfrage). Orange: Linien des gewählten Entwurfs. Farbige Wege: Rufbus-Fahrzeuge (Kreise = Abholung und Ziel) im Zeitfenster ±20 Minuten.")

report = build_report(
    "Rufbus oder Linienbus: Szenario-Bericht",
    [("Anfragen je Stunde", settings.lam), ("Gebiet", f"{settings.area} x {settings.area} km"), ("Haltepunkte", settings.stops), ("Wartezeit (max.)", f"{int(settings.wait)} min"),
     ("Umwegfaktor", de(settings.detour)), ("Plaetze", settings.cap), ("Verfahren", ev.PROC_LABEL[settings.proc]), ("Qualitaetsmass", ev.MEASURE_LABEL[settings.measure]),
     ("Linienfuehrung", ev.DESIGN_LABEL[a.design]), ("Zufalls-Seed", settings.seed)],
    [("Fahrzeuge Rufbus", f"{a.K:.0f}"), ("Fahrzeuge Linienbus", f"{a.N:.0f}" if a.N != INF else "nicht erreichbar"),
     ("Fahrzeugstunden je Fahrgast Rufbus", de(a.ruf_cost, 3)), ("Fahrzeugstunden je Fahrgast Linienbus", de(a.line_cost, 3) if a.line_cost != INF else "-"),
     ("Mittlere Reisezeit Rufbus (min)", de(a.ruf["total"])), ("Mittlere Reisezeit Linienbus (min)", de(linie_total) if linie_total is not None else "-")],
    verdict_text.replace("**", ""),
    ["Modell: Luftlinie bei 30 km/h, 0,5 min Halt, Messfenster 45 bis 315 min; Kosten = Flottenstunden der ganzen Betriebsdauer je bedientem Fahrgast, keine Euro-Kosten.",
     "Ein einzelnes Szenario streut; die Messreihe der Demo (30 Zufalls-Seeds je Zelle) zeigt, was typisch ist."],
)
st.download_button("📄 Szenario-Bericht als PDF herunterladen", report, file_name="rufbus_szenario.pdf", mime="application/pdf", key="pdf_button")

st.markdown("---")

# --- Wo kippt es? --------------------------------------------------------------------------------------------------------------------------

st.markdown("## 📐 Wo kippt es?")
try:
    variants = R.variants()
    base = variants[0]
    labels = [c["label"] for c in variants]
    st.markdown(
        "**Vorgerechnet, nicht live:** Fahrzeugstunden je Fahrgast über die Nachfragedichte, Mittel über 30 Zufalls-Seeds je Dichte. Die Einstellung hier ist **unabhängig von den Reglern links**, "
        "weil nur Einzelabweichungen vom Basisfall (FCFS, 4 Plätze, Umweg 1,5, Wartezeit 15 min, 10 × 10 km, 30 Haltepunkte) vorgerechnet sind."
    )
    c1, c2 = st.columns(2)
    sel = c1.selectbox("Variante und Qualitätsmaß der Messreihe", labels, key="variant_select")
    des = c2.selectbox("Linienführung der Kurve", ev.DESIGN_OPTIONS, key="curve_design_select", format_func=lambda v: ev.DESIGN_LABEL[v])
    cell = variants[labels.index(sel)]
    dens = R.densities() if cell.get("L", 10.0) == 10.0 else R.densities()[: len(cell["ruf_mean"])]
    b = None
    if cell is base and base.get("ruf_cost_p10"):
        b = (base["ruf_cost_p10"], base["ruf_cost_p90"])
    st.plotly_chart(build_cost_curves(cell, dens, design=des, base_band=b), width="stretch", key=f"curve_{labels.index(sel)}_{des}")
    cx = cell["crossing"] if des == "best" else cell["crossing_by_design"].get(des, cell["crossing_fixed"])
    k1, k2, k3 = st.columns(3)
    k1.metric("Kipppunkt (Anfragen je km² und Stunde)", R.fmt_crossing(cx))
    k2.metric("Kipppunkt (Anfragen je Stunde im Gebiet)", R.lam_text({"lam_cross": (cx * cell.get("L", 10.0) ** 2) if (cx is not None and math.isfinite(cx)) else cx}))
    k3.metric("Bootstrap-Band (P10 bis P90)", R.boot_text(cell) if des == "best" else "-")
    st.caption("Logarithmische Achsen. Wo die blaue Kurve unter der orangen liegt, ist der Rufbus billiger. Ohne Schnittpunkt im untersuchten Bereich: kein Kipppunkt (Rufbus überall billiger oder Linienbus überall billiger).")
except FileNotFoundError:
    st.info("Die vorgerechnete Messreihe (data/ruf_results.json) fehlt in dieser Installation.")
    variants = []

st.markdown("---")

# --- Skalenerträge -------------------------------------------------------------------------------------------------------------------------

st.markdown("## 📈 Skalenerträge und Bündeln")
try:
    rows = R.base_rows()
    xs = [math.log(r["lam"]) for r in rows]
    ys = [math.log(r["K_mean"]) for r in rows]
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sum((x - mx) ** 2 for x in xs)
    s1, s2 = st.columns(2)
    with s1:
        st.markdown(f"**Flotte gegen Nachfrage.** Der Rufbus braucht nur so viele Fahrzeuge, wie die Nachfrage verlangt: K* wächst mit λ^{de(slope, 2)}, "
                    f"die Fahrzeugstunden je Fahrgast fallen von {de(rows[0]['cost'][0], 2)} auf {de(rows[-1]['cost'][0], 2)}.")
        st.plotly_chart(build_scaling(rows, slope), width="stretch", key="scaling")
    with s2:
        st.markdown("**Bündeln.** Mit mehr Fahrtwünschen sitzen mehr Fahrgäste mit anderen im Fahrzeug; das spart Flotte gegenüber Einzelfahrten (1 Platz).")
        st.plotly_chart(build_pooling(R.load()["pooling"]), width="stretch", key="pooling")
    cf = R.load()["cap_f"]
    tab = pd.DataFrame([{"Dichte je km² und Stunde": de(r["dens"], 2), "Flotte, 4 Plätze": de(b_["K_mean"], 2), "8 Plätze statt 4": f"{r['c8_f1.5'][0]:+.2f}".replace(".", ","),
                         "Umweg 2,0 statt 1,5": f"{r['c4_f2.0'][0]:+.2f}".replace(".", ","), "1 Platz statt 4": f"{r['c1_f1.5'][0]:+.2f}".replace(".", ",")}
                        for r, b_ in zip(cf, rows)])
    st.dataframe(tab, width="stretch", hide_index=True)
    st.caption("Differenz der Mindestflotte gegen die Basis in Fahrzeugen (Mittel über 30 Zufalls-Seeds). 8 statt 4 Plätze ändert die Flotte praktisch nicht; der Umwegfaktor wirkt stärker als zusätzliche Plätze.")
except FileNotFoundError:
    pass

st.markdown("---")

# --- Methodenvergleich ---------------------------------------------------------------------------------------------------------------------

with st.expander("🔧 Wie wir das erreichen – vollständiger Methodenvergleich"):
    tab_proc, tab_line, tab_exact, tab_data = st.tabs(["🚐 Rufbus-Verfahren", "🚌 Linienbus", "🧮 Exakt (kleine Instanzen)", "📈 Messreihe"])

    with tab_proc:
        st.markdown("Drei Wege, Fahrtwünsche Fahrzeugen zuzuteilen: **sofortige Einfügung** (billigste zulässige Position), **Einfügen + Verbessern** (danach Umlegen und Austauschen) und **Batch** "
                    "(alle Wünsche eines 5-Minuten-Fensters gemeinsam). Der Vergleich läuft auf Ihrem Szenario bei der Flotte, die oben für Ihr Verfahren berechnet wurde.")
        if st.button("Verfahren auf diesem Szenario vergleichen", key="proc_start"):
            st.session_state["proc_done"] = settings
        if st.session_state.get("proc_done") == settings:
            with st.spinner("Rechne die drei Verfahren …"):
                out = []
                for p in ev.PROC_OPTIONS:
                    sim = S.run_ruf(world, float(settings.lam), int(a.K), settings.cap, settings.wait, settings.detour, proc=p, search_seed=settings.seed * 100)
                    r = summarize(sim)
                    out.append({"Verfahren": ev.PROC_LABEL[p], f"Servicegrad bei {a.K:.0f} Fahrzeugen": f"{100 * r['served']:.1f} %".replace(".", ","),
                                "Wartezeit (min)": de(r["wait"]), "Fahrzeit (min)": de(r["ride"]), "Gebündelt (Fahrgäste mit Mitfahrern)": f"{100 * r['shared']:.0f} %"})
            st.dataframe(pd.DataFrame(out), width="stretch", hide_index=True)
        try:
            pt = R.load()["proc_vs_fcfs"]
            st.plotly_chart(build_proc(pt, {"ols": "Einfügen + Verbessern", "batch": "Batch 5 min + Verbessern", "batch0": "Batch 5 min, nur Einfügen"}), width="stretch", key="proc_chart")
            st.caption("Vorgerechnet: Flottengröße minus Flottengröße bei sofortiger Einfügung (Mittel ± Standardfehler, 30 Zufalls-Seeds). Warten auf den Stapel braucht **mehr** Fahrzeuge, weil das Wartezeitbudget bei der Anfrage beginnt; "
                       "Einfügen + Verbessern spart erst bei hoher Dichte etwas.")
        except FileNotFoundError:
            pass

    with tab_line:
        st.markdown(f"Linienbus mit dem Entwurf **{ev.DESIGN_LABEL[a.design]}** ({len(a.lines)} Linie{'n' if len(a.lines) != 1 else ''}), Fahrzeuge gleichmäßig verteilt, periodischer Fahrplan mit Zufallsphase, "
                    "Wegewahl nach erwarteter Zeit (Wartezeit = halber Takt je Einstieg, 1 Minute je Umstieg).")
        dfd = pd.DataFrame([{"Entwurf": ev.DESIGN_LABEL[d], "Fahrzeuge N*": (f"{n:.0f}" if n != INF else "nicht erreichbar"),
                             "Fahrzeugstunden je Fahrgast": (de(c, 3) if c != INF else "-")} for d, (n, c) in a.by_design.items()])
        st.dataframe(dfd, width="stretch", hide_index=True)
        if a.line:
            lc = a.line
            st.markdown(f"Gewählter Entwurf: mittlere Wartezeit {de(lc.get('wait', 0))} min, Fahrzeit {de(lc.get('ride', 0))} min, Gesamtzeit {de(lc.get('total', 0))} min; "
                        f"erreichbar {100 * lc['reach']:.0f} %; Anteil, der das Rufbus-Versprechen (Wartezeit höchstens 15 min, Umweg höchstens 1,5) hielte: {100 * lc.get('env_15_1.5', 0):.0f} %; "
                        f"Auslastung der Plätze höchstens {100 * lc['rho']:.0f} % (Kapazität ist nie der Engpass).".replace(".", ","))
        st.caption("Teilabdeckungs-Entwürfe (P1, P2) bedienen nur Haltepunkte im Fußweg-Einzugsbereich; der Fußweg steckt in der Gesamtzeit, nicht in der Wartezeit.")

    with tab_exact:
        st.markdown("Ein **Los** von wenigen gleichzeitig bekannten Fahrtwünschen: Hier lässt sich das Optimum noch **aufzählen** (alle Reihenfolgen, freies Abwarten erlaubt). "
                    "Das zeigt im Kleinen, wie weit die Heuristiken vom Optimum entfernt sind. Es ist ein **Lehrstück, keine Betriebsaussage**: Auf Flottenebene schrumpft der Abstand auf wenige Prozent.")
        e1, e2 = st.columns(2)
        en = e1.slider("Anzahl Anfragen im Los", 4, 8, 6, key="exact_n")
        ek = e2.selectbox("Fahrzeuge", (1, 2, 3), key="exact_k")
        key = (settings, en, ek)
        if st.button("Exakt lösen (alle Reihenfolgen aufzählen)", key="exact_start"):
            st.session_state["exact_done"] = key
        if st.session_state.get("exact_done") == key:
            with st.spinner("Zähle alle Reihenfolgen auf …"):
                rng = SplitMix64(settings.seed + 777)
                allr = [r for r in world.requests(120.0) if 60.0 <= r[0] < 200.0]
                rng.shuffle(allr)
                pool = sorted(allr[:en])
                reqs = [(0.0, o, d) for _, o, d in pool]
                starts = world.starts[:ek]
                rel = [0.0] * len(reqs)
                ddl = [r + settings.wait for r in rel]
                rmax = [settings.detour * (world.tt[o][d] + C.DWELL) + C.SLACK for _, o, d in reqs]
                ro = [r[1] for r in reqs]
                rd = [r[2] for r in reqs]
                served, cost, complete, nodes = exact_solve_flex(starts, rel, ddl, rmax, ro, rd, world.tt, C.DWELL, settings.cap, node_limit=1_500_000)
                res = {}
                sim = Sim(world.tt, reqs, ek, starts, settings.cap, settings.wait, settings.detour)
                sim.run_fcfs()
                res["Sofortige Einfügung"] = (sum(1 for x in sim.status if x == 1), sum(b - a_ for a_, b in sim.busy))
                sim = Sim(world.tt, reqs, ek, starts, settings.cap, settings.wait, settings.detour)
                sim.advance(0.0)
                sim.plan_batch(list(range(len(reqs))), 0.0, SplitMix64(settings.seed))
                sim.advance(INF)
                res["Batch + Verbessern (alle Wünsche gemeinsam)"] = (sum(1 for x in sim.status if x == 1), sum(b - a_ for a_, b in sim.busy))
                hs, hc = offline_heuristic(starts, rel, ddl, rmax, ro, rd, world.tt, C.DWELL, settings.cap)
                res["Offline-Heuristik"] = (hs, hc)
            rows_e = [{"Verfahren": "Exakt (Aufzählung)", "Bediente Anfragen": served, "Anteil des Exakten": "100 %", "Fahr- und Haltezeit (min)": de(cost)}]
            for name, (s_, c_) in res.items():
                rows_e.append({"Verfahren": name, "Bediente Anfragen": s_, "Anteil des Exakten": f"{100 * s_ / served:.0f} %" if served else "-", "Fahr- und Haltezeit (min)": de(c_)})
            st.dataframe(pd.DataFrame(rows_e), width="stretch", hide_index=True)
            st.caption(f"Los von {len(reqs)} Anfragen, {ek} Fahrzeug(e), Wartezeit {int(settings.wait)} min. " + ("Aufzählung vollständig." if complete else "Knotengrenze erreicht: Der exakte Wert ist nicht bewiesen.")
                       + " Kosten nur bei gleich vielen bedienten Anfragen vergleichbar.")

    with tab_data:
        try:
            tbl = pd.DataFrame([{"Dichte je km² und Stunde": de(r["dens"], 2), "Anfragen je Stunde": f"{r['lam']:.0f}", "Flotte K* (Mittel ± SE)": f"{de(r['K_mean'], 1)} ± {de(r['K_se'], 2)}",
                                 "Median (P10 bis P90)": f"{r['K_med']:.0f} ({r['K_p10']:.0f} bis {r['K_p90']:.0f})", "Wartezeit (min)": de(r["wait"]), "Fahrzeit (min)": de(r["ride"]),
                                 "Fahrgäste mit Mitfahrern": f"{100 * r['shared']:.0f} %", "Fahrzeugstunden je Fahrgast": de(r["cost"][0], 3)} for r in R.base_rows()])
            st.dataframe(tbl, width="stretch", hide_index=True)
            m = R.meta()
            if m:
                st.caption(f"Basiszelle der Messreihe (FCFS, 4 Plätze, Umweg 1,5, Wartezeit 15 min, 10 × 10 km, 30 Haltepunkte). Insgesamt {m.get('n_runs', '?')} Läufe in {m.get('n_cells', '?')} Zellen mit je 30 Zufalls-Seeds.")
        except FileNotFoundError:
            pass

st.markdown("---")

with st.expander("Wie funktioniert diese Demo?"):
    st.markdown(
        """
**Szenario.** Ein quadratisches Gebiet mit 20 bis 40 Haltepunkten; die Nachfrage zwischen den Haltepunkten ist ungleich verteilt (ein Teil konzentriert sich auf zwei Zentren). Fahrtwünsche kommen über einen Betriebstag
von 6 Stunden; gemessen wird zwischen Minute 45 und 315, weil das System leer startet.

**Rufbus.** Jede Anfrage wird sofort angenommen oder abgelehnt: Abholung höchstens W Minuten nach der Anfrage, Fahrzeit höchstens Umwegfaktor mal Direktfahrt plus 2 Minuten, Platzgrenze beachtet. Zugeteilt wird dem Fahrzeug,
bei dem die Route am wenigsten länger wird. **Flotte K\\***: die kleinste Flottengröße, ab der mindestens 90 % der Fahrtwünsche angenommen werden (und bei jeder größeren Flotte ebenso).

**Linienbus.** Feste Linien, Fahrzeuge gleichmäßig verteilt, periodischer Fahrplan. Wegewahl nach erwarteter Zeit; ausgewertet wird gegen den echten Fahrplan. **N\\***: die kleinste Fahrzeugzahl, die dasselbe Qualitätsmaß erreicht wie der Rufbus.

**Was „gleich gut“ heißt.** Gleiche mittlere Wartezeit ist ein Maß; gleiche mittlere Gesamtreisezeit ein anderes. Der Linienbus wartet im Mittel gleich lang, fährt aber über Umwege entlang der Linie länger. Die Demo zeigt beide Maße nebeneinander.

**Live und Messreihe.** Ein Szenario streut von Zufalls-Seed zu Zufalls-Seed. Deshalb steht die vorgerechnete Messreihe (30 Zufalls-Seeds je Zelle) daneben, und die Meldung vergleicht mit ihr.

**Annahmen, die die Demo setzt** (Wer setzt an: die Demo, nicht Sie):

| Annahme | Wert | Wirkung |
|---|---|---|
| Fahrgeschwindigkeit | 30 km/h auf der Luftlinie | skaliert alle Zeiten |
| Halt je Aufnahme oder Absetzen | 0,5 min | wirkt auf Fahrzeit und Flotte |
| Kosten | Flottenstunden der ganzen Betriebsdauer je bedientem Fahrgast, keine Euro-Kosten | bei gefahrenen statt bezahlten Stunden rückt der Kipppunkt nach oben |
| Linienentwürfe | sieben feste Entwürfe, keine Linienführung nach Nachfrage | der „faire Linienbus“ ist nicht eindeutig |
| Rufbus | keine Leerfahrten-Neupositionierung, keine Vorbestellung, keine Fahrerpausen | macht den Rufbus eher günstiger |
"""
    )

with st.expander("📐 Mathematische Formulierung"):
    # erklaerseite:lesehilfe:start (erzeugt von tools/set_demo_explainer.py (Website-Repo) aus tools/content/explainers/rufbus-oder-linienbus-erklaert.json, nicht von Hand ändern)
    st.markdown(
        r"""
**Lesehilfe.** Gegeben sind ein Gebiet mit Haltepunkten, die Fahrtwünsche pro Stunde und die Qualitätsgrenzen für den Rufbus (Wartezeit, Umweg, Plätze). Gesucht sind die kleinste Flotte des Rufbusses und die kleinste Fahrzeugzahl des Linienbusses bei gleicher Qualität, daraus die Kosten je Fahrgast und der Kipppunkt, an dem beide Kosten gleich sind.

| Symbol | Bedeutung |
|---|---|
| $t$, $o$, $d$ | Anfragezeit, Start und Ziel eines Fahrtwunsches |
| $a_p$, $a_d$ | Abholzeit und Ankunftszeit am Ziel |
| $W$, $f$ | höchste Wartezeit, Umwegfaktor |
| $t_{od}$, $\delta$, $s$ | Direktfahrzeit, Halt je Aufnahme oder Absetzen, Aufschlag |
| $K^*$, $K'$ | kleinste Flotte des Rufbusses, eine beliebige größere Flotte |
| $N^*$, $N'$, $C$, $h$ | kleinste Fahrzeugzahl des Linienbusses, eine größere Zahl, Umlaufzeit, Takt |
| $c_{\text{Ruf}}$, $c_{\text{Linie}}$ | Fahrzeugstunden je Fahrgast bei Rufbus und Linienbus |
| $T$, $n_{\text{bedient}}$, $n_{\text{Anfragen}}$ | Messfenster, bediente Fahrgäste, Zahl der Anfragen im Fenster |

[Schritt für Schritt erklärt, mit Herleitung und Literatur](https://sebastianhanisch.net/rufbus-oder-linienbus-erklaert.html#fachleute)
        """
    )
    # erklaerseite:lesehilfe:end
    st.markdown("**Rufbus.** Für jede angenommene Anfrage mit Anfragezeit $t$, Start $o$ und Ziel $d$ gilt für Abholzeit $a_p$ und Ankunftszeit $a_d$ am Ziel:")
    st.latex(r"a_p \le t + W")
    st.latex(r"a_d - a_p \le f\,(t_{od} + \delta) + s")
    st.markdown("mit höchster Wartezeit $W$, Umwegfaktor $f$, Direktfahrzeit $t_{od}$, Halt $\\delta = 0{,}5$ min und Aufschlag $s = 2$ min; die Last darf die Platzzahl nicht überschreiten. Die Flotte ist")
    st.latex(r"K^* = \min\{K : \text{Servicegrad}(K') \ge 0{,}9 \text{ für alle } K' \ge K\}")
    st.markdown("**Linienbus.** Bei Umlaufzeit $C$ und $N$ Fahrzeugen ist der Takt $h = C/N$, die mittlere Wartezeit je Einstieg $h/2$ (plus 1 Minute je Umstieg).")
    st.latex(r"N^* = \min\{N : \text{Maß}(N') \text{ erfüllt für alle } N' \ge N\}")
    st.markdown("**Kosten je Fahrgast.** Fahrzeugstunden je Fahrgast bei Messfenster $T = 4{,}5$ h:")
    st.latex(r"c_{\text{Ruf}} = \frac{K^*\,T}{n_{\text{bedient}}}, \qquad c_{\text{Linie}} = \frac{N^*\,T}{n_{\text{Anfragen}}\cdot \text{Erreichbarkeit}}")
    st.markdown("Der **Kipppunkt** ist die Dichte, bei der beide Kurven gleich sind (log-linear zwischen den gemessenen Dichten interpoliert; Bootstrap über die Zufalls-Seeds).")

st.markdown("---")
st.caption(
    "Diese Demo ist Teil des Portfolios von [Sebastian Hanisch](https://sebastianhanisch.net) – "
    "Operations Research und Machine Learning ([Über mich](https://sebastianhanisch.net/ueber-mich.html)). "
    "Mehr zum Thema: [ÖPNV und Fernverkehr optimieren](https://sebastianhanisch.net/oepnv-fernverkehr-optimierung.html)."
)
