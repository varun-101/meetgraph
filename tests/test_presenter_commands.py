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


def test_mark_as_done_is_update():
    intent = parse_intent_fallback("mark the payment gateway task as done", TITLES)
    assert intent["action"] == "update_action"
    assert intent["item"] == "payment gateway task"
    assert intent["status"] == "done"
    intent = parse_intent_fallback("set billing migration to in progress", TITLES)
    assert intent["action"] == "update_action" and intent["status"] == "in_progress"


def test_assign_is_update_owner():
    intent = parse_intent_fallback("assign the billing migration to Max", TITLES)
    assert intent["action"] == "update_action"
    assert intent["item"] == "the billing migration"
    assert intent["owner_name"] == "Max"


def test_add_action_item_is_create():
    intent = parse_intent_fallback("add action item: write the deploy runbook", TITLES)
    assert intent["action"] == "create_action"
    assert intent["text"] == "write the deploy runbook"


def test_mark_with_unknown_status_falls_through():
    # "mark X as urgent" — not a status we know; must not become a broken write
    intent = parse_intent_fallback("mark the gateway task as urgent", TITLES)
    assert intent["action"] != "update_action"


def test_match_action_item():
    from api.presenter.bot import match_action_item

    items = [
        ("a", "Finish the payment gateway integration by August 30th"),
        ("b", "Migrate the billing schema draft to Postgres next week"),
    ]
    matched, ties = match_action_item(items, "payment gateway task")
    assert matched == "a" and ties == 1
    matched, ties = match_action_item(items, "billing migration")
    assert matched == "b"
    matched, _ = match_action_item(items, "quarterly offsite planning")
    assert matched is None
