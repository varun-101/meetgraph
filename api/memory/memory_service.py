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
        await cognee.cognify(datasets=datasets, user=user, graph_model=build_graph_model())

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
        import cognee
        from cognee import SearchType

        user = await self._get_org_user(org_id)
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
        """Normalize cognee SearchResult list → {answer, citations, raw}."""
        answer_parts: list[str] = []
        citations: list[str] = []
        raw: list[Any] = []
        flat: list[Any] = []
        for r in results or []:
            if isinstance(r, list):
                flat.extend(r)
            else:
                flat.append(r)
        for r in flat:
            raw.append(str(r))
            if isinstance(r, str):
                text = r
            elif isinstance(r, dict):
                text = str(r.get("text") or r.get("answer") or r.get("search_result") or r)
                for ref in r.get("references") or r.get("citations") or []:
                    citations.append(str(ref))
            else:
                text = str(r)
            # cognee appends an "Evidence:" block when include_references is on
            if "Evidence:" in text:
                answer, _, evidence = text.partition("Evidence:")
                answer_parts.append(answer.strip())
                citations.extend(
                    line.strip(" -•") for line in evidence.strip().splitlines() if line.strip()
                )
            else:
                answer_parts.append(text)
        return {"answer": "\n\n".join(p for p in answer_parts if p), "citations": citations, "raw": raw}


# process-wide singleton (async-safe: worst case is a duplicate user lookup)
memory_service = MemoryService()
