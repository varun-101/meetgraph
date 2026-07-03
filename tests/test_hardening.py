"""P5 hardening: rate limiter windows + GDPR local-artifact purge."""
import uuid
from pathlib import Path

import pytest

from api import ratelimit


@pytest.fixture(autouse=True)
def clean_limiter():
    ratelimit._hits.clear()
    yield
    ratelimit._hits.clear()


def test_login_rate_limit_blocks_sixth_attempt():
    for _ in range(5):
        assert ratelimit.check("1.2.3.4", "/auth/jwt/login", "POST") is None
    wait = ratelimit.check("1.2.3.4", "/auth/jwt/login", "POST")
    assert wait is not None and wait > 0


def test_limits_are_per_ip_and_per_rule():
    for _ in range(5):
        assert ratelimit.check("1.2.3.4", "/auth/jwt/login", "POST") is None
    # different IP unaffected
    assert ratelimit.check("5.6.7.8", "/auth/jwt/login", "POST") is None
    # same IP, different rule unaffected
    assert ratelimit.check("1.2.3.4", "/memory/search", "POST") is None


def test_unmatched_paths_never_limited():
    for _ in range(1000):
        assert ratelimit.check("1.2.3.4", "/health", "GET") is None


@pytest.mark.asyncio
async def test_purge_local_artifacts(session, world, tmp_path, monkeypatch):
    from api.config import settings
    from api.memory.router import purge_local_artifacts
    from api.models import ActionItem, Meeting, Recording, SyncState, Transcript

    monkeypatch.setattr(settings, "recordings_dir", tmp_path)
    project = world["projects"]["x"]

    meeting_id = uuid.uuid4()
    wav_dir = tmp_path / str(meeting_id)
    wav_dir.mkdir(parents=True)
    wav = wav_dir / "u1.wav"
    wav.write_bytes(b"RIFFxxxx")
    deck_dir = (tmp_path / "decks").resolve()
    deck_dir.mkdir(parents=True)
    deck = deck_dir / f"{meeting_id}.html"
    deck.write_text("<html></html>")

    session.add(
        Meeting(
            id=meeting_id, project_id=project.id, title="m",
            livekit_room=f"mg_{meeting_id}", status="ready",
        )
    )
    await session.flush()
    session.add(Recording(meeting_id=meeting_id, participant_identity="u1", file_path=str(wav)))
    session.add(Transcript(meeting_id=meeting_id, canonical_text="hi", json_utterances=[]))
    session.add(
        ActionItem(meeting_id=meeting_id, project_id=project.id, text="do", status="open")
    )
    session.add(SyncState(key=f"brief:{project.id}", value="{}"))
    await session.commit()

    result = await purge_local_artifacts(session, project.id)
    await session.commit()

    assert result["meetings_purged"] == 1
    assert result["files_removed"] >= 2  # wav + deck
    assert not wav.exists()
    assert not deck.exists()
    assert await session.get(Transcript, meeting_id) is None
    assert await session.get(SyncState, f"brief:{project.id}") is None
    # meeting row survives as calendar history
    assert await session.get(Meeting, meeting_id) is not None
