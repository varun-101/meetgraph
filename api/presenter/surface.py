"""Render a DeckSpec to one self-contained HTML file (vault-graphite styling,
palette values mirrored from web/app/globals.css). Slides switch via
window.showSlide(n) — driven by Playwright in bot.py."""
from __future__ import annotations

import html
import json
import uuid
from pathlib import Path

from api.config import settings
from api.presenter.deck import DeckSpec

_CSS = """
* { margin: 0; padding: 0; box-sizing: border-box; }
html, body { width: 1280px; height: 720px; overflow: hidden; }
body {
  background: #0c0f13; color: #e8edf4;
  font-family: 'Segoe UI', system-ui, sans-serif;
  -webkit-font-smoothing: antialiased;
}
.slide {
  display: none; width: 1280px; height: 720px;
  padding: 72px 96px; flex-direction: column;
}
.slide.active { display: flex; }
.kicker {
  font-family: Consolas, monospace; font-size: 15px; letter-spacing: 0.12em;
  text-transform: uppercase; color: #3ddc97; margin-bottom: 18px;
}
h1 { font-size: 54px; font-weight: 650; letter-spacing: -0.02em; line-height: 1.1; }
h2 { font-size: 42px; font-weight: 650; letter-spacing: -0.02em; margin-bottom: 40px; }
ul { list-style: none; margin-top: 8px; }
li {
  font-size: 27px; color: #aab4c4; line-height: 1.45;
  padding: 14px 0 14px 34px; position: relative;
  border-bottom: 1px solid #1d232d;
}
li::before {
  content: ""; position: absolute; left: 4px; top: 27px;
  width: 10px; height: 10px; border-radius: 3px; background: #2ba572;
}
.footer {
  margin-top: auto; display: flex; justify-content: space-between;
  font-family: Consolas, monospace; font-size: 14px; color: #5c6678;
}
.title-slide { justify-content: center; }
.title-slide .sub { margin-top: 22px; font-size: 24px; color: #8c96a8; }
.brand b { color: #3ddc97; }
"""


def render_deck(deck: DeckSpec, meeting_id: uuid.UUID) -> Path:
    """Write the deck HTML; returns the file path (bot loads it as file://...)."""
    n = len(deck.slides)
    slides_html = []
    for i, slide in enumerate(deck.slides):
        bullets = "\n".join(f"<li>{html.escape(b)}</li>" for b in slide.bullets)
        if i == 0:
            body = (
                f'<div class="kicker">meetgraph &middot; presented from project memory</div>'
                f"<h1>{html.escape(slide.title)}</h1>"
                + (f'<div class="sub">{html.escape(deck.title)}</div>' if deck.title != slide.title else "")
                + (f"<ul>{bullets}</ul>" if slide.bullets else "")
            )
            cls = "slide title-slide"
        else:
            body = f'<div class="kicker">{html.escape(deck.title)}</div><h2>{html.escape(slide.title)}</h2><ul>{bullets}</ul>'
            cls = "slide"
        footer = (
            f'<div class="footer"><span class="brand">meet<b>graph</b> presenter</span>'
            f"<span>{i + 1} / {n}</span></div>"
        )
        slides_html.append(f'<section class="{cls}" id="s{i}">{body}{footer}</section>')

    doc = (
        "<!doctype html><html><head><meta charset='utf-8'>"
        f"<title>{html.escape(deck.title)}</title><style>{_CSS}</style></head><body>"
        + "".join(slides_html)
        + "<script>"
        f"var COUNT={n};"
        "window.showSlide=function(n){"
        "document.querySelectorAll('.slide').forEach(function(s){s.classList.remove('active')});"
        "var el=document.getElementById('s'+n); if(el){el.classList.add('active')} return n;};"
        "window.showSlide(0);"
        "</script></body></html>"
    )

    # resolve(): recordings_dir may be relative, and Path.as_uri() (used for
    # the browser's file:// URL) requires an absolute path
    out_dir = (Path(settings.recordings_dir) / "decks").resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{meeting_id}.html"
    path.write_text(doc, encoding="utf-8")
    # sidecar with narration for debugging/replay
    (out_dir / f"{meeting_id}.json").write_text(
        json.dumps(deck.model_dump(), indent=2), encoding="utf-8"
    )
    return path
