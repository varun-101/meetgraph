"""Deck generation: project memory → DeckSpec via DeepSeek JSON mode.

Same client pattern as api/memory/extractor.py. Degrades to a DB-only fallback
deck if the LLM call fails — the presenter must always have something to show.
"""
from __future__ import annotations

import json
import logging
import uuid

from pydantic import BaseModel, ValidationError
from sqlalchemy import select

from api.config import settings
from api.db import async_session_maker
from api.models import ActionItem, Meeting, Project, SyncState, User

log = logging.getLogger(__name__)

MAX_SLIDES = 8

SYSTEM = """You create a short slide deck for a live meeting presentation.
Return STRICT JSON:
{"title": str, "slides": [{"title": str, "bullets": [str, ...], "narration": str}]}
Rules: 3-6 slides. 2-5 bullets each, short (max 12 words). `narration` is what
a presenter SAYS for that slide - spoken prose, 2-4 sentences, natural, no
markdown, mention people by name and cite which meeting a fact came from.
Slide 1 is a title/overview slide. Cover: recent decisions, open action items
(with owners/deadlines), active topics. Only use facts from the provided
material - never invent."""


class Slide(BaseModel):
    title: str
    bullets: list[str] = []
    narration: str = ""


class DeckSpec(BaseModel):
    title: str
    slides: list[Slide]


async def build_deck(project_id: uuid.UUID) -> DeckSpec:
    """Gather material (cached brief + DB rows) and ask DeepSeek for a deck."""
    async with async_session_maker() as session:
        project = await session.get(Project, project_id)
        if project is None:
            raise ValueError(f"project {project_id} not found")

        brief_row = await session.get(SyncState, f"brief:{project_id}")
        brief_md = ""
        if brief_row and brief_row.value:
            try:
                brief_md = json.loads(brief_row.value).get("markdown", "")
            except ValueError:
                pass

        actions = (
            await session.execute(
                select(ActionItem)
                .where(ActionItem.project_id == project_id, ActionItem.status != "done")
                .order_by(ActionItem.created_at)
            )
        ).scalars().all()
        owner_ids = [a.owner_user_id for a in actions if a.owner_user_id]
        owners = {}
        if owner_ids:
            rows = (
                await session.execute(select(User).where(User.id.in_(owner_ids)))
            ).scalars().all()
            owners = {u.id: (u.name or u.email) for u in rows}

        meetings = (
            await session.execute(
                select(Meeting)
                .where(Meeting.project_id == project_id, Meeting.status == "ready")
                .order_by(Meeting.created_at.desc())
                .limit(5)
            )
        ).scalars().all()

    action_lines = [
        f"- {a.text} (owner: {owners.get(a.owner_user_id, 'unassigned')}"
        + (f", due {a.deadline.date().isoformat()}" if a.deadline else "")
        + f", status: {a.status})"
        for a in actions
    ]
    meeting_lines = [f"- {m.title} ({(m.started_at or m.created_at).date().isoformat()})" for m in meetings]

    material = (
        f"Project: {project.name}\n\n"
        f"Pre-meeting brief:\n{brief_md or '(no brief yet)'}\n\n"
        f"Open action items:\n" + ("\n".join(action_lines) or "(none)") + "\n\n"
        f"Recent meetings:\n" + ("\n".join(meeting_lines) or "(none)")
    )

    deck = await _llm_deck(project.name, material)
    if deck is not None:
        deck.slides = deck.slides[:MAX_SLIDES]
        return deck
    return _fallback_deck(project.name, action_lines, meeting_lines)


async def _llm_deck(project_name: str, material: str) -> DeckSpec | None:
    if not settings.llm_api_key:
        return None
    try:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(base_url=settings.llm_endpoint, api_key=settings.llm_api_key)
        resp = await client.chat.completions.create(
            model=settings.llm_model.split("/")[-1],
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": material[:16000]},
            ],
            temperature=0.3,
        )
        return parse_deck(resp.choices[0].message.content or "")
    except Exception:
        log.exception("deck generation failed — using fallback deck")
        return None


def parse_deck(raw: str) -> DeckSpec | None:
    """Strict-parse LLM output; None on any shape problem (caller falls back)."""
    try:
        data = json.loads(raw)
        deck = DeckSpec.model_validate(data)
        return deck if deck.slides else None
    except (ValueError, ValidationError):
        return None


def _fallback_deck(
    project_name: str, action_lines: list[str], meeting_lines: list[str]
) -> DeckSpec:
    """DB-only deck when the LLM is unavailable. Terse but truthful."""
    slides = [
        Slide(
            title=f"{project_name} — status",
            bullets=[f"{len(action_lines)} open action items", f"{len(meeting_lines)} recent meetings"],
            narration=f"Here is a quick status overview for {project_name}.",
        )
    ]
    if action_lines:
        slides.append(
            Slide(
                title="Open action items",
                bullets=[line.lstrip("- ")[:80] for line in action_lines[:5]],
                narration="These are the currently open action items for the project.",
            )
        )
    if meeting_lines:
        slides.append(
            Slide(
                title="Recent meetings",
                bullets=[line.lstrip("- ")[:80] for line in meeting_lines[:5]],
                narration="And these are the recent meetings this summary draws from.",
            )
        )
    return DeckSpec(title=f"{project_name} — project brief", slides=slides)
