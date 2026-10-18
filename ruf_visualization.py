"""Plotly-Abbildungen. Alle Achsen sind gesperrt (fixedrange), damit Touch-Geräte beim Scrollen nicht am Diagramm hängen bleiben."""

import math

import plotly.graph_objects as go

import ruf_constants as C

PALETTE = ["#1f6fb2", "#2a9d8f", "#8e44ad", "#d35400", "#16a085", "#7f8c8d", "#2c3e50", "#b03a2e", "#117a65", "#6c3483", "#af601a", "#1b4f72", "#7d6608", "#7b241c"]


def lock_axes(fig):
    fig.update_xaxes(fixedrange=True)
    fig.update_yaxes(fixedrange=True)
    return fig


def _base(fig, height=380, legend_y=-0.28):
    fig.update_layout(height=height, margin=dict(l=10, r=10, t=10, b=10), legend=dict(orientation="h", y=legend_y), plot_bgcolor="rgba(0,0,0,0)")
    return lock_axes(fig)


# ------------------------------------------------------------------------------------------------------------------------------ Karte
def routes_at(sim, t_min, span):
    """Je Fahrzeug die Folge der Halte, die im Fenster [t - span, t + span] angefahren werden (plus der Halt davor, damit der Weg zusammenhängt)."""
    out = {}
    for v in sim.vs:
        log = sorted(v.log)
        sel = [i for i, (a, s, r, isd) in enumerate(log) if t_min - span <= a <= t_min + span]
        if not sel:
            continue
        lo = max(0, sel[0] - 1)
        out[v.id] = [(log[i][1], log[i][0], log[i][3]) for i in range(lo, sel[-1] + 1)]
    return out


def build_map(a, t_min, span=20.0):
    """Haltepunkte (Größe nach Nachfrage), Linien des gewählten Entwurfs, Wege der Rufbus-Fahrzeuge im Zeitfenster um t_min."""
    w = a.world
    L = w.L
    fig = go.Figure()
    for k, ln in enumerate(a.lines):
        xs = [float(w.coords[s][0]) for s in ln.stops]
        ys = [float(w.coords[s][1]) for s in ln.stops]
        fig.add_trace(go.Scatter(x=xs, y=ys, mode="lines", line=dict(color=C.COLOR_LINE, width=4), opacity=0.55, hoverinfo="skip",
                                 name="Linienbus" if k == 0 else None, showlegend=(k == 0), legendgroup="line"))
    trails = routes_at(a.sim, t_min, span) if a.sim is not None else {}
    first = True
    for vid, seq in sorted(trails.items()):
        xs = [float(w.coords[s][0]) for s, _, _ in seq]
        ys = [float(w.coords[s][1]) for s, _, _ in seq]
        fig.add_trace(go.Scatter(x=xs, y=ys, mode="lines+markers", line=dict(color=PALETTE[vid % len(PALETTE)], width=2), marker=dict(size=5, symbol="circle-open"),
                                 hovertemplate=f"Rufbus {vid + 1}<br>Halt %{{customdata}}<extra></extra>", customdata=[f"{t:.0f} min ({'Ziel' if d else 'Abholung'})" for _, t, d in seq],
                                 name="Rufbus (Wege im Zeitfenster)" if first else None, showlegend=first, legendgroup="ruf"))
        first = False
    dem = [int(v) for v in w.demand.sum(axis=1)]
    mx = max(dem) or 1
    fig.add_trace(go.Scatter(x=[float(c[0]) for c in w.coords], y=[float(c[1]) for c in w.coords], mode="markers",
                             marker=dict(size=[6 + 14 * d / mx for d in dem], color=C.COLOR_STOP, line=dict(width=1, color="white")),
                             hovertemplate="Haltepunkt %{customdata[0]}<br>Nachfrage %{customdata[1]}<extra></extra>", customdata=[[i + 1, d] for i, d in enumerate(dem)],
                             name="Haltepunkte (Größe = Nachfrage)"))
    pad = 0.04 * L
    fig.update_xaxes(range=[-pad, L + pad], title_text="km", constrain="domain")
    fig.update_yaxes(range=[-pad, L + pad], title_text="km", scaleanchor="x", scaleratio=1)
    return _base(fig, height=520, legend_y=-0.15)


# ------------------------------------------------------------------------------------------------------------------------------ Kostenkurven
def _vals(seq):
    return [None if (v is None or v == float("inf") or v == float("-inf")) else v for v in seq]


def build_cost_curves(c, dens, design="best", base_band=None):
    """Fahrzeugstunden je Fahrgast über die Nachfragedichte (logarithmische Achsen) für eine Kipppunkt-Zelle `c`.
    design: best (je Instanz bester Entwurf), sonst ein Entwurf, falls die Zelle `line_mean_by_design` enthält."""
    xs = list(dens)
    ruf = c["ruf_mean"]
    if design == "best":
        line = c["line_mean_oracle"]
        cx = c["crossing"]
        lname = "Linienbus (bester Entwurf je Instanz)"
    else:
        per = c.get("line_mean_by_design", {})
        line = per.get(design) or c["line_mean_fixed"]
        cx = c["crossing_by_design"].get(design, c["crossing_fixed"])
        lname = f"Linienbus ({design})"
    fig = go.Figure()
    if base_band:
        fig.add_trace(go.Scatter(x=xs + xs[::-1], y=list(base_band[1]) + list(base_band[0])[::-1], fill="toself", fillcolor="rgba(31,111,178,0.15)",
                                 line=dict(width=0), hoverinfo="skip", name="Rufbus P10 bis P90 (Zufalls-Seeds)"))
    fig.add_trace(go.Scatter(x=xs, y=_vals(ruf), mode="lines+markers", line=dict(color=C.COLOR_RUF, width=3), name="Rufbus",
                             hovertemplate="Dichte %{x}: %{y:.3f} Fahrzeugstunden je Fahrgast<extra></extra>"))
    fig.add_trace(go.Scatter(x=xs, y=_vals(line), mode="lines+markers", line=dict(color=C.COLOR_LINE, width=3), name=lname,
                             hovertemplate="Dichte %{x}: %{y:.3f} Fahrzeugstunden je Fahrgast<extra></extra>"))
    if cx is not None and math.isfinite(cx):
        fig.add_vline(x=cx, line_dash="dot", line_color="#1c2430", annotation_text=f"Kipppunkt {cx:.2f}".replace(".", ","), annotation_position="top left")
        lo, hi = c.get("boot_p10"), c.get("boot_p90")
        if lo is not None and design == "best":
            fig.add_vrect(x0=lo, x1=hi, fillcolor="rgba(28,36,48,0.08)", line_width=0)
    fig.update_xaxes(type="log", title_text="Anfragen je Stunde und km²", tickvals=[0.03, 0.06, 0.1, 0.2, 0.4, 0.6, 1], ticktext=["0,03", "0,06", "0,1", "0,2", "0,4", "0,6", "1"])
    fig.update_yaxes(type="log", title_text="Fahrzeugstunden je Fahrgast", tickvals=[0.05, 0.1, 0.2, 0.5, 1, 2, 5], ticktext=["0,05", "0,1", "0,2", "0,5", "1", "2", "5"])
    return _base(fig)


def build_scaling(rows, slope):
    """Rufbus-Flotte K* gegen Anfragen je Stunde (log-log) mit Anpassung K* ~ lambda^b."""
    xs = [r["lam"] for r in rows]
    ys = [r["K_mean"] for r in rows]
    se = [r["K_se"] for r in rows]
    a = math.exp(sum(math.log(y) for y in ys) / len(ys) - slope * sum(math.log(x) for x in xs) / len(xs))
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=xs, y=ys, mode="markers+lines", error_y=dict(type="data", array=se, visible=True), line=dict(color=C.COLOR_RUF, width=3), name="Flotte K* (Mittel ± Standardfehler)",
                             hovertemplate="%{x} Anfragen/h: %{y:.2f} Fahrzeuge<extra></extra>"))
    fig.add_trace(go.Scatter(x=xs, y=[a * x ** slope for x in xs], mode="lines", line=dict(color="#7f8c8d", dash="dash"), name=f"Anpassung ∝ λ^{slope:.2f}".replace(".", ","), hoverinfo="skip"))
    fig.update_xaxes(type="log", title_text="Anfragen je Stunde (Gebiet 10 × 10 km)", tickvals=[3, 6, 10, 20, 40, 60, 100], ticktext=["3", "6", "10", "20", "40", "60", "100"])
    fig.update_yaxes(type="log", title_text="Fahrzeuge für Servicegrad ≥ 90 %", tickvals=[2, 3, 5, 8, 12, 16], ticktext=["2", "3", "5", "8", "12", "16"])
    return _base(fig, height=340)


def build_proc(proc_tab, labels):
    """Differenz der Flottengröße zu sofortiger Einfügung (Fahrzeuge) je Dichte, je Verfahren, mit Standardfehler."""
    fig = go.Figure()
    for k, (key, rows) in enumerate(proc_tab.items()):
        fig.add_trace(go.Scatter(x=[r["dens"] for r in rows], y=[r["diff_mean"] for r in rows], mode="lines+markers", name=labels.get(key, key),
                                 error_y=dict(type="data", array=[r["diff_se"] for r in rows], visible=True), line=dict(color=PALETTE[k * 2 % len(PALETTE)], width=2.5),
                                 hovertemplate="Dichte %{x}: %{y:+.2f} Fahrzeuge<extra></extra>"))
    fig.add_hline(y=0, line_dash="dot", line_color="#7f8c8d")
    fig.update_xaxes(type="log", title_text="Anfragen je Stunde und km²", tickvals=[0.03, 0.06, 0.1, 0.2, 0.4, 0.6, 1], ticktext=["0,03", "0,06", "0,1", "0,2", "0,4", "0,6", "1"])
    fig.update_yaxes(title_text="Flotte minus Flotte bei sofortiger Einfügung")
    return _base(fig, height=340)


def build_pooling(rows):
    """Anteil der Fahrgäste, die mit anderen im Fahrzeug sitzen, über die Dichte (Plätze 4, Umweg 1,5 und 2,0)."""
    xs = [r["dens"] for r in rows]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=xs, y=[100 * r["c4_f1.5"]["shared"] for r in rows], mode="lines+markers", name="Umweg 1,5", line=dict(color=C.COLOR_RUF, width=3)))
    fig.add_trace(go.Scatter(x=xs, y=[100 * r["c4_f2.0"]["shared"] for r in rows], mode="lines+markers", name="Umweg 2,0", line=dict(color="#2a9d8f", width=3)))
    fig.update_xaxes(type="log", title_text="Anfragen je Stunde und km²", tickvals=[0.03, 0.06, 0.1, 0.2, 0.4, 0.6, 1], ticktext=["0,03", "0,06", "0,1", "0,2", "0,4", "0,6", "1"])
    fig.update_yaxes(title_text="Fahrgäste mit Mitfahrern (%)", range=[0, 100])
    return _base(fig, height=320)
