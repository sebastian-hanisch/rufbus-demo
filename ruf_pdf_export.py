"""Szenario-Bericht als PDF (fpdf2, Kernschrift: nur Latin-1; Sonderzeichen werden ersetzt)."""

from fpdf import FPDF

_ERSATZ = {"≥": ">=", "≤": "<=", "²": "2", "×": "x", "∝": "~", "–": "-", "—": "-", "„": '"', "“": '"', "→": "->", "±": "+/-", "·": "*"}


def _s(text):
    for k, v in _ERSATZ.items():
        text = text.replace(k, v)
    return text.encode("latin-1", "replace").decode("latin-1")


def build_report(title, settings_rows, metric_rows, verdict_text, notes):
    """settings_rows / metric_rows: Listen von (Bezeichnung, Wert); verdict_text: Meldung; notes: Liste von Absätzen. Rückgabe: Bytes."""
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 15)
    pdf.multi_cell(0, 8, _s(title), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)
    for head, rows in (("Einstellungen", settings_rows), ("Kennzahlen", metric_rows)):
        pdf.set_font("Helvetica", "B", 11)
        pdf.cell(0, 7, _s(head), new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 10)
        for k, v in rows:
            pdf.cell(80, 6, _s(k), border="B")
            pdf.cell(0, 6, _s(str(v)), border="B", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(3)
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 7, "Ergebnis", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    pdf.multi_cell(0, 5.5, _s(verdict_text), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)
    pdf.set_font("Helvetica", "I", 9)
    for n in notes:
        pdf.multi_cell(0, 5, _s(n), new_x="LMARGIN", new_y="NEXT")
        pdf.ln(1)
    return bytes(pdf.output())
