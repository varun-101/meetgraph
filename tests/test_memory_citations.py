"""Temporal routing heuristic, citation parsing with doc capture, and
doc-hash → meeting enrichment mapping."""
import hashlib
import uuid

import pytest

from api.memory.memory_service import _parse_citations, wants_temporal


def test_wants_temporal():
    assert wants_temporal("when did we decide the launch date?")
    assert wants_temporal("what changed since last week")
    assert wants_temporal("show me the latest decision on billing")
    assert not wants_temporal("what did we decide about MongoDB?")
    assert not wants_temporal("who owns the payment gateway task")


def test_parse_citations_captures_doc_name():
    evidence = (
        '\n- chunk 1 of document text_92291deac6ddbafc5eb521204cc53b95 '
        '(data_id: 99e61461, chunk_id: 56b582b2): "[source: meeting] '
        '[project: Apollo] [participants: Max, Mia] [date: 2026-07-03] '
        'Meeting: test meet [00:02] Max: Hello there"'
    )
    cites = _parse_citations(evidence)
    assert len(cites) == 1
    c = cites[0]
    assert c["doc"] == "text_92291deac6ddbafc5eb521204cc53b95"
    assert c["source"] == "test meet"
    assert c["date"] == "2026-07-03"
    assert "Hello there" in c["snippet"]


@pytest.mark.asyncio
async def test_docmap_recorded_and_resolvable(session, world):
    from api.memory.pipeline import _record_doc_mapping
    from api.models import Meeting, SyncState

    project = world["projects"]["x"]
    meeting_id = uuid.uuid4()
    session.add(
        Meeting(
            id=meeting_id, project_id=project.id, title="planning sync",
            livekit_room=f"mg_{meeting_id}", status="ready",
        )
    )
    doc = "[source: meeting] [project: X] ...\nMeeting: planning sync\n\nhello"
    await _record_doc_mapping(session, doc, meeting_id)
    await session.commit()

    expected_key = f"docmap:text_{hashlib.md5(doc.encode('utf-8')).hexdigest()}"
    row = await session.get(SyncState, expected_key)
    assert row is not None and row.value == str(meeting_id)

    # idempotent on re-ingest
    await _record_doc_mapping(session, doc, meeting_id)
    await session.commit()
    assert (await session.get(SyncState, expected_key)).value == str(meeting_id)
