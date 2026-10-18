"""Footer: die App endet mit dem Portfolio-Absatz, und die README hat denselben Absatz als letzten.

Der genaue Wortlaut kommt aus tools/set_demo_footer.py im Website-Repo (`python tools/set_demo_footer.py --only <slug> --apply`
schreibt ihn in app.py und README.md). Dieser Test prüft deshalb nur die Struktur und bleibt grün, wenn der Wortlaut dort geändert wird."""

import re
from pathlib import Path

from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parent.parent
MARKER = "Diese Demo ist Teil des Portfolios von [Sebastian Hanisch](https://sebastianhanisch.net)"


def _footer_caption():
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=180)
    at.run()
    assert not at.exception, [str(e) for e in at.exception]
    captions = [c.value for c in at.caption if MARKER in c.value]
    assert len(captions) == 1
    return captions[0]


def test_app_footer_links_home_about_me_and_one_portfolio_page():
    text = _footer_caption()
    assert "(https://sebastianhanisch.net/ueber-mich.html)" in text
    assert re.search(r"\]\(https://sebastianhanisch\.net/[a-z0-9-]+\.html\)\.$", text)
    assert "Kontakt aufnehmen" not in text


def test_readme_ends_with_the_same_footer_paragraph():
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", (ROOT / "README.md").read_text(encoding="utf-8")) if p.strip()]
    assert paragraphs[-1] == _footer_caption()
