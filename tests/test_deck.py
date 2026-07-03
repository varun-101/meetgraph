"""Presenter deck: LLM-output parsing, fallback deck, and surface rendering.
No network, no cognee, no browser."""
import json
import uuid

from api.presenter.deck import DeckSpec, Slide, _fallback_deck, parse_deck


def test_parse_valid_deck():
    raw = json.dumps(
        {
            "title": "Apollo — status",
            "slides": [
                {"title": "Overview", "bullets": ["a", "b"], "narration": "Welcome."},
                {"title": "Decisions", "bullets": ["launch Sept 17"], "narration": "We decided."},
            ],
        }
    )
    deck = parse_deck(raw)
    assert deck is not None
    assert deck.title == "Apollo — status"
    assert len(deck.slides) == 2
    assert deck.slides[1].bullets == ["launch Sept 17"]


def test_parse_garbage_returns_none():
    assert parse_deck("not json at all") is None
    assert parse_deck(json.dumps({"title": "x"})) is None          # missing slides
    assert parse_deck(json.dumps({"title": "x", "slides": []})) is None  # empty
    assert parse_deck(json.dumps({"slides": [{"bullets": []}]})) is None  # bad shapes


def test_fallback_deck_from_db_lines():
    deck = _fallback_deck(
        "Apollo",
        ["- Fix gateway (owner: Max, status: open)"],
        ["- test meet (2026-07-03)"],
    )
    assert deck.slides  # always at least the status slide
    titles = [s.title for s in deck.slides]
    assert any("action" in t.lower() for t in titles)
    assert all(s.narration for s in deck.slides)


def test_render_deck_html(tmp_path, monkeypatch):
    from api.config import settings

    monkeypatch.setattr(settings, "recordings_dir", tmp_path)
    from api.presenter.surface import render_deck

    deck = DeckSpec(
        title="Apollo",
        slides=[
            Slide(title="Overview <script>", bullets=["x & y"], narration="hi"),
            Slide(title="Actions", bullets=["do it"], narration="next"),
        ],
    )
    meeting_id = uuid.uuid4()
    path = render_deck(deck, meeting_id)
    html_text = path.read_text(encoding="utf-8")
    assert path.exists()
    assert "showSlide" in html_text
    assert "Overview &lt;script&gt;" in html_text  # escaped
    assert "x &amp; y" in html_text
    assert 'id="s1"' in html_text
    # narration sidecar for debugging
    assert (tmp_path / "decks" / f"{meeting_id}.json").exists()
