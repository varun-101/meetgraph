"""V2 browse mode: the presenter drives the real Next.js app in its shared
browser — visible cursor, scripted read-only tours, template narration from DB
rows (deterministic; no LLM latency mid-tour).

A tour is a list of (selector | None, narration) steps: move the fake cursor
to the selector (if any), then speak. Auth: a short-lived JWT minted for the
commanding user is planted in localStorage, so the bot sees exactly what the
person who asked could see.
"""
from __future__ import annotations

import uuid

from sqlalchemy import select

from api.db import async_session_maker
from api.models import ActionItem, Meeting, Transcript, User

# route builders per browse target
ROUTES = {
    "actions": lambda pid, mid: f"/projects/{pid}/actions",
    "brief": lambda pid, mid: f"/projects/{pid}/brief",
    "dashboard": lambda pid, mid: "/dashboard",
    "transcript": lambda pid, mid: f"/meetings/{mid}",
}

_CURSOR_JS = """
(() => {
  if (document.getElementById('mg-cursor')) return;
  const c = document.createElement('div');
  c.id = 'mg-cursor';
  c.style.cssText = `position:fixed;left:640px;top:360px;width:22px;height:22px;
    z-index:99999;pointer-events:none;transition:left .6s cubic-bezier(.4,0,.2,1),
    top .6s cubic-bezier(.4,0,.2,1);filter:drop-shadow(0 2px 6px rgba(0,0,0,.6))`;
  c.innerHTML = `<svg viewBox="0 0 24 24" width="22" height="22">
    <path d="M4 2 L4 19 L8.5 15 L11.5 21.5 L14 20.3 L11 14 L17 14 Z"
      fill="#3ddc97" stroke="#0c0f13" stroke-width="1.2"/></svg>`;
  document.body.appendChild(c);
})()
"""


async def inject_cursor(page) -> None:
    await page.evaluate(_CURSOR_JS)


async def move_cursor(page, selector: str) -> bool:
    """Glide the overlay cursor to the element's center; scrolls it into view.
    Returns False if the element doesn't exist (tour keeps going)."""
    el = await page.query_selector(selector)
    if el is None:
        return False
    await el.scroll_into_view_if_needed()
    box = await el.bounding_box()
    if box is None:
        return False
    x, y = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
    await page.evaluate(
        f"(()=>{{const c=document.getElementById('mg-cursor');"
        f"if(c){{c.style.left='{x:.0f}px';c.style.top='{y:.0f}px';}}}})()"
    )
    # real mouse move too, so CSS hover states fire on the toured element
    await page.mouse.move(x, y)
    return True


async def ensure_app_auth(page, token: str, web_origin: str) -> None:
    """Plant the bearer token before the app boots, then land on the app."""
    await page.goto(f"{web_origin}/login", wait_until="domcontentloaded")
    await page.evaluate(f"localStorage.setItem('meetgraph_token', '{token}')")


async def build_tour(
    target: str, project_id: uuid.UUID
) -> tuple[str | None, list[tuple[str | None, str]]]:
    """Return (meeting_id_for_route | None, [(selector, narration), ...]).
    Narration is templated from DB rows — deterministic and instant."""
    async with async_session_maker() as session:
        if target == "actions":
            rows = (
                await session.execute(
                    select(ActionItem)
                    .where(ActionItem.project_id == project_id, ActionItem.status != "done")
                    .order_by(ActionItem.created_at)
                )
            ).scalars().all()
            owner_ids = [a.owner_user_id for a in rows if a.owner_user_id]
            owners = {}
            if owner_ids:
                users = (
                    await session.execute(select(User).where(User.id.in_(owner_ids)))
                ).scalars().all()
                owners = {u.id: (u.name or u.email) for u in users}
            steps: list[tuple[str | None, str]] = [
                (None, f"This is the live action tracker. There are {len(rows)} open items.")
            ]
            for n, a in enumerate(rows[:4]):
                owner = owners.get(a.owner_user_id, "unassigned")
                due = f", due {a.deadline.date().isoformat()}" if a.deadline else ""
                steps.append(
                    (f"ul > li:nth-child({n + 1})", f"{a.text}. Owner: {owner}{due}.")
                )
            if not rows:
                steps.append((None, "Nothing is open right now — the board is clear."))
            return None, steps

        if target == "brief":
            return None, [
                (None, "Here is the pre-meeting brief, generated from this project's "
                       "knowledge graph and cached until the memory changes."),
                (".markdown h2, .markdown h1, .markdown strong",
                 "It covers recent decisions, open action items, and active topics, "
                 "each cited back to the meeting it came from."),
            ]

        if target == "transcript":
            meeting = (
                await session.execute(
                    select(Meeting)
                    .where(Meeting.project_id == project_id, Meeting.status == "ready")
                    .order_by(Meeting.created_at.desc())
                    .limit(1)
                )
            ).scalars().first()
            if meeting is None:
                return None, [(None, "There is no finished meeting with a transcript yet.")]
            transcript = await session.get(Transcript, meeting.id)
            count = len(transcript.json_utterances or []) if transcript else 0
            steps = [
                (None, f"This is the transcript of {meeting.title} — {count} utterances, "
                       "each attributed to its speaker from their own audio track."),
                ("ol > li:nth-child(1)", "It starts here."),
            ]
            if count > 2:
                steps.append(
                    (f"ol > li:nth-child({min(count, 4)})",
                     "Every line is clickable evidence — this is what answers cite.")
                )
            return str(meeting.id), steps

        # dashboard (default)
        meetings = (
            await session.execute(
                select(Meeting).where(Meeting.project_id == project_id)
            )
        ).scalars().all()
        ready = sum(1 for m in meetings if m.status == "ready")
        return None, [
            (None, f"The project dashboard: {len(meetings)} meetings, "
                   f"{ready} fully processed into memory."),
        ]
