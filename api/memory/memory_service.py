"""MemoryService — the single place cognee is touched (§8: version-churn shield,
model-swap seam, cognee Cloud seam).

Pinned: cognee==1.2.2 (verified 2026-07-03 against docs.cognee.ai + source at
tag v1.2.2). Key deviations from the original plan discovered in research:

- There is NO `set_workspace(org_id)`. Current model: User → Tenant → dataset
  ACLs, with `user=` passed per call. We map workspace≈org by running one
  cognee *service user* per org; all of an org's datasets are owned by its
  service user, so name-based `datasets=[...]` scoping resolves only within
  the org — the hard isolation boundary the plan wanted.
- ENABLE_BACKEND_ACCESS_CONTROL must be TRUE (it defaults on for the
  postgres+pgvector combo): with it off, `datasets=` filters are silently
  ignored at query time, which would break isolation entirely. In this mode
  cognee CREATEs a database per dataset — the Postgres role needs CREATEDB.
- `add/cognify/search` are "legacy" (fully supported); `forget(dataset=...)`
  is the current deletion API.

cognee Cloud seam (D2): set COGNEE_BASE_URL + COGNEE_API_KEY and swap this
class's calls for the hosted REST client; the interface stays identical.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import uuid
from typing import Any

from api.config import settings

log = logging.getLogger(__name__)


class MemoryUnavailable(RuntimeError):
    """cognee not installed/configured — callers surface 503, never crash."""


def _org_email(org_id: uuid.UUID) -> str:
    # NOT .local/.internal — cognee's email validator rejects special-use TLDs
    return f"org-{org_id}@meetgraph.dev"


def _org_password(org_id: uuid.UUID) -> str:
    return hmac.new(
        settings.jwt_secret.encode(), f"cognee:{org_id}".encode(), hashlib.sha256
    ).hexdigest()


class MemoryService:
    """All cognee calls for one process. Dataset names ALWAYS come from the
    §4.4 resolver — never from user input."""

    def __init__(self) -> None:
        self._org_users: dict[uuid.UUID, Any] = {}
        self._migrated = False

    async def _ensure_ready(self) -> None:
        """One-time cognee schema init (fresh DBs need startup migrations)."""
        if self._migrated:
            return
        try:
            from cognee.modules.engine.operations.setup import setup
        except ImportError as exc:
            raise MemoryUnavailable("cognee is not installed") from exc
        await setup()  # creates cognee's relational + pgvector schemas if absent
        self._migrated = True

    # ----- org (workspace) resolution -----

    async def _get_org_user(self, org_id: uuid.UUID):
        """Get-or-create the org's cognee service user (workspace≈org seam)."""
        if org_id in self._org_users:
            return self._org_users[org_id]
        await self._ensure_ready()
        try:
            from cognee.modules.users.methods import create_user
        except ImportError as exc:
            raise MemoryUnavailable("cognee is not installed") from exc

        email, password = _org_email(org_id), _org_password(org_id)
        user = None
        try:
            user = await create_user(email, password)
        except Exception:
            # already exists → look it up
            try:
                from cognee.modules.users.methods import get_user_by_email

                user = await get_user_by_email(email)
            except ImportError:
                # method name may differ across versions — fall back to authenticate
                from cognee.modules.users.methods import authenticate_user

                user = await authenticate_user(email, password)
        if user is None:
            raise MemoryUnavailable(f"could not resolve cognee user for org {org_id}")
        self._org_users[org_id] = user
        return user

    # ----- core ops (audit rows are written by callers alongside these) -----

    async def add(self, org_id: uuid.UUID, dataset: str, text: str) -> None:
        import cognee

        user = await self._get_org_user(org_id)
        await cognee.add(text, dataset_name=dataset, user=user)

    async def cognify(self, org_id: uuid.UUID, datasets: list[str]) -> None:
        import cognee

        from api.memory.ontology import build_graph_model

        user = await self._get_org_user(org_id)
        # temporal_cognify: meetings are inherently temporal — decisions
        # supersede each other; time-aware graph lets TEMPORAL search prefer
        # the latest state ("what did we decide last week?").
        await cognee.cognify(
            datasets=datasets,
            user=user,
            graph_model=build_graph_model(),
            temporal_cognify=True,
        )

    async def search(
        self,
        org_id: uuid.UUID,
        datasets: list[str],
        query: str,
        search_type: str = "GRAPH_COMPLETION",
        top_k: int = 10,
    ) -> dict:
        """Cited Q&A. Returns {answer, citations, raw}. `datasets` must come
        from allowed_datasets(); an empty list is refused here as a backstop."""
        if not datasets:
            return {"answer": "", "citations": [], "raw": []}
        from cognee.modules.data.exceptions.exceptions import DatasetNotFoundError

        user = await self._get_org_user(org_id)

        # Time-flavored questions route to TEMPORAL first (data is cognified
        # with temporal_cognify); fall back to the requested type if empty.
        tried_temporal = False
        try:
            if search_type == "GRAPH_COMPLETION" and wants_temporal(query):
                tried_temporal = True
                result = await self._search_inner(user, datasets, query, "TEMPORAL", top_k)
                if result["answer"].strip():
                    return await _enrich_citations(result)
            result = await self._search_inner(user, datasets, query, search_type, top_k)
            return await _enrich_citations(result)
        except DatasetNotFoundError:
            # Project exists but nothing ingested yet — empty memory, not an error.
            return {"answer": "", "citations": [], "raw": []}
        except Exception:
            if not tried_temporal:
                raise
            # TEMPORAL can fail on datasets ingested before the temporal flag —
            # degrade to the plain graph search rather than erroring.
            log.exception("TEMPORAL search failed — retrying with %s", search_type)
            result = await self._search_inner(user, datasets, query, search_type, top_k)
            return await _enrich_citations(result)

    async def _search_inner(self, user, datasets, query, search_type, top_k) -> dict:
        import cognee
        from cognee import SearchType

        results = await cognee.search(
            query_text=query,
            query_type=getattr(SearchType, search_type, SearchType.GRAPH_COMPLETION),
            user=user,
            datasets=datasets,
            top_k=top_k,
            include_references=True,  # docs contradict on the default — be explicit
        )
        return self._shape_results(results)

    async def forget_dataset(self, org_id: uuid.UUID, dataset: str) -> None:
        """§4.2: admin-only (enforced by caller). GDPR path P5."""
        import cognee

        user = await self._get_org_user(org_id)
        await cognee.forget(dataset=dataset, user=user)

    # ----- helpers -----

    @staticmethod
    def _shape_results(results: Any) -> dict:
        """Normalize cognee search output → {answer, citations, raw}.

        Observed shape (1.2.2, multi-user mode): a list of per-dataset dicts
        {dataset_id, dataset_name, search_result: [str, ...]} where each string
        may carry an "Evidence:" block when include_references is on.
        """
        answer_parts: list[str] = []
        citations: list[dict] = []
        raw: list[str] = []

        texts: list[str] = []
        for r in results or []:
            if isinstance(r, dict):
                sr = r.get("search_result") or r.get("text") or r.get("answer")
                if isinstance(sr, (list, tuple)):
                    texts.extend(str(x) for x in sr)
                elif sr is not None:
                    texts.append(str(sr))
                else:
                    texts.append(str(r))
            elif isinstance(r, (list, tuple)):
                texts.extend(str(x) for x in r)
            else:
                texts.append(str(r))

        for text in texts:
            raw.append(text)
            if "Evidence:" in text:
                answer, _, evidence = text.partition("Evidence:")
                answer_parts.append(answer.strip())
                citations.extend(_parse_citations(evidence))
            else:
                answer_parts.append(text.strip())

        return {"answer": "\n\n".join(p for p in answer_parts if p), "citations": citations, "raw": raw}


def _parse_citations(evidence: str) -> list[dict]:
    """Turn cognee's Evidence block into UI-friendly citations.

    Raw shape per item:
      - chunk 1 of document text_<hash> (data_id: ..., chunk_id: ...): "[source:
        meeting] [project: X] ... Meeting: <title> [00:02] Alice: ..."
    We surface the human part (meeting title + snippet) and keep the ids as a
    compact ref for debugging.
    """
    import re

    out: list[dict] = []
    # Items start with "- chunk"; the block may arrive as one long line.
    for item in re.split(r"\n- |\A- ", evidence.strip()):
        item = item.strip().strip("-• ")
        if not item:
            continue
        m = re.match(r'(?s)(chunk \d+) of document (\S+) \(([^)]*)\):\s*"(.*)"?\s*$', item)
        if m:
            snippet = m.group(4).strip().strip('"')
            title_m = re.search(r"Meeting: (.+?) \[", snippet)
            date_m = re.search(r"\[date: ([0-9-]+)\]", snippet)
            # drop the doc-header tags from the preview; keep the speech
            speech = re.sub(r"^\[source:.*?\]\s*Meeting: .*?(?=\[\d)", "", snippet).strip()
            out.append(
                {
                    "source": (title_m.group(1) if title_m else "meeting"),
                    "date": date_m.group(1) if date_m else None,
                    "snippet": (speech or snippet)[:280],
                    "ref": m.group(1),
                    "doc": m.group(2),  # text_<md5> — resolved to a meeting below
                }
            )
        else:
            out.append({"source": None, "date": None, "snippet": item[:280], "ref": None})
    return out


def wants_temporal(query: str) -> bool:
    """Heuristic: does this question care about time/ordering of events?"""
    q = f" {query.lower()} "
    hints = (
        "when ", " latest", " last week", " last month", " yesterday", " today",
        " recently", " this week", " timeline", " history", " over time",
        " since ", " before ", " after ", " first ", " most recent", " changed",
    )
    return any(h in q for h in hints)


async def _enrich_citations(result: dict) -> dict:
    """Resolve each citation's cognee doc name (text_<md5>) to a meeting via
    the docmap recorded at ingest time — citations become clickable links."""
    docs = {c.get("doc") for c in result.get("citations", []) if isinstance(c, dict) and c.get("doc")}
    if not docs:
        return result
    try:
        from sqlalchemy import select

        from api.db import async_session_maker
        from api.models import Meeting, SyncState

        async with async_session_maker() as session:
            rows = (
                await session.execute(
                    select(SyncState).where(SyncState.key.in_([f"docmap:{d}" for d in docs]))
                )
            ).scalars().all()
            doc_to_meeting = {r.key.removeprefix("docmap:"): r.value for r in rows}
            meeting_ids = {uuid.UUID(v) for v in doc_to_meeting.values()}
            meetings = {}
            if meeting_ids:
                mrows = (
                    await session.execute(select(Meeting).where(Meeting.id.in_(meeting_ids)))
                ).scalars().all()
                meetings = {str(m.id): m for m in mrows}

        for c in result.get("citations", []):
            if not isinstance(c, dict):
                continue
            mid = doc_to_meeting.get(c.get("doc") or "")
            meeting = meetings.get(mid) if mid else None
            if meeting is not None:
                c["meeting_id"] = mid
                c["source"] = meeting.title
                if meeting.started_at and not c.get("date"):
                    c["date"] = meeting.started_at.date().isoformat()
    except Exception:  # enrichment is best-effort — plain citations still render
        log.exception("citation enrichment failed")
    return result


# process-wide singleton (async-safe: worst case is a duplicate user lookup)
memory_service = MemoryService()
