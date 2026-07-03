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


def test_browse_needs_show_verb():
    intent = parse_intent_fallback("show the action tracker", TITLES)
    assert intent["action"] == "browse" and intent["target"] == "actions"
    intent = parse_intent_fallback("open the transcript", TITLES)
    assert intent["action"] == "browse" and intent["target"] == "transcript"
    # a question that merely mentions the last meeting stays a memory question
    intent = parse_intent_fallback("what did we decide in the last meeting?", TITLES)
    assert intent["action"] == "answer"


def test_bare_target_is_browse():
    intent = parse_intent_fallback("dashboard", TITLES)
    assert intent["action"] == "browse" and intent["target"] == "dashboard"
    intent = parse_intent_fallback("slides", TITLES)
    assert intent["action"] == "browse" and intent["target"] == "deck"
