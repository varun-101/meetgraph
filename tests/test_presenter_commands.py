"""V1 directable presenter: heuristic intent fallback (no LLM, no network)."""
from api.presenter.bot import parse_intent_fallback

TITLES = ["Apollo — status", "Recent Decisions", "Open Action Items", "Active Topics"]


def test_nav_keywords():
    assert parse_intent_fallback("next", TITLES)["action"] == "next"
    assert parse_intent_fallback("Next slide", TITLES)["action"] == "next"
    assert parse_intent_fallback("go back", TITLES)["action"] == "prev"


def test_title_match_goes_to_slide():
    intent = parse_intent_fallback("show the open action items", TITLES)
    assert intent["action"] == "goto"
    assert intent["slide_index"] == 2


def test_question_falls_through_to_answer():
    intent = parse_intent_fallback("what did we decide about the launch date?", TITLES)
    assert intent["action"] == "answer"
    assert intent["query"] == "what did we decide about the launch date?"


def test_single_word_overlap_is_not_a_goto():
    # "decisions" alone overlaps one title word — too weak, treat as question
    intent = parse_intent_fallback("decisions?", TITLES)
    assert intent["action"] == "answer"
