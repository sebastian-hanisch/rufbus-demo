"""Fester Kopf: der Titel bleibt beim Scrollen oben (Gerüst aus tools/new_demo.py, DEMO-PLAYBOOK §2 und §3).

Der Titel steht in `with st.container(key="kopf")`; Streamlit gibt dem Element die CSS-Klasse `st-key-kopf`, an der das Stylesheet
ansetzt. Verwendung in der App: `st.html(kopf_css(dunkles_design()))`, danach der Container."""

import streamlit as st

# Hintergrundfarben der beiden Standard-Designs von Streamlit; der feste Kopf braucht einen deckenden Hintergrund,
# damit der darunter durchlaufende Inhalt nicht durchscheint.
HINTERGRUND_HELL = "#ffffff"
HINTERGRUND_DUNKEL = "#0e1117"


def dunkles_design() -> bool:
    """Läuft die App im dunklen Streamlit-Design? Ohne Angabe (z. B. in Tests) gilt das helle."""
    try:
        return st.context.theme.type == "dark"
    except Exception:
        return False


_KOPF_CSS = """
<style>
/* Streamlit legt um einen Container mit key einen Wrapper gleicher Höhe: dieser muss kleben, sonst endet das
   Kleben mit dem Wrapper. Der Container selbst klebt als Rückfall für Versionen ohne Wrapper.
   `top` lässt Platz für die feste Streamlit-Kopfleiste. */
[data-testid="stLayoutWrapper"]:has(> .st-key-kopf),
.st-key-kopf {
  position: sticky;
  top: 3.75rem;
  z-index: 990;
  background-color: __HINTERGRUND__;
}
.st-key-kopf {
  padding: 0.25rem 0 0.5rem 0;
  border-bottom: 1px solid rgba(128, 128, 128, 0.3);
}
.st-key-kopf h1 { font-size: 1.5rem; padding: 0; line-height: 1.25; }
/* Streamlits Markdown-Container hat margin-bottom: -1rem; ohne diese Zeile ist der Kopf 16 px niedriger als der Titel,
   und der darunter durchlaufende Inhalt scheint am unteren Rand des Titels durch. */
.st-key-kopf [data-testid="stMarkdownContainer"] { margin-bottom: 0; }
/* Auf dem Telefon frisst ein fester Kopf zu viel vom Fenster: dort scrollt er mit. */
@media (max-width: 640px) {
  [data-testid="stLayoutWrapper"]:has(> .st-key-kopf),
  .st-key-kopf { position: static; }
  .st-key-kopf h1 { font-size: 1.15rem; }
}
</style>
"""


def kopf_css(dunkel: bool) -> str:
    """Stylesheet des festen Kopfes; der Hintergrund folgt dem Streamlit-Design."""
    return _KOPF_CSS.replace("__HINTERGRUND__", HINTERGRUND_DUNKEL if dunkel else HINTERGRUND_HELL)
