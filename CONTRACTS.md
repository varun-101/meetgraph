# CONTRACTS.md — module boundaries for parallel build

This file is the single source of truth for cross-module interfaces. Build agents
own disjoint subtrees and may NOT edit files outside their subtree; anything
crossing a boundary goes through the contracts below. Orchestrator owns:
`api/main.py`, `api/config.py`, `api/db.py`, `.env.template`, this file, `infra/`.

## Ownership map

| Subtree | Owner agent | Contents |
|---|---|---|
| `api/models.py`, `api/deps.py`, `api/auth/`, `api/rbac/`, `tests/` | **api-core** | SQLAlchemy models (all §5.1 tables), fastapi-users auth, RBAC resolver + guards, audit, isolation tests |
| `api/meetings/`, `api/capture/`, `stt/` | **meetings-capture** | rooms, LiveKit tokens, webhooks, lifecycle, recorder bot, STT worker, assembler |
| `api/memory/` | **memory** | MemoryService, ontology.py, extractor, search/brief routers |
| `web/` | **web** | Next.js app |

## Shared imports (provided by orchestrator)

```python
from api.config import settings          # pydantic-settings, all env vars typed
from api.db import get_session, async_session_maker, Base
```

## Provided by api-core (everyone else imports, never redefines)

```python
from api.models import (User, Org, OrgMember, Project, ProjectMember, Meeting,
                        MeetingGuest, Recording, Transcript, ActionItem, AuditLog)
from api.deps import current_active_user            # fastapi-users dependency
from api.rbac.resolver import allowed_datasets      # §4.4 chokepoint — ONLY source of dataset names
from api.rbac.audit import write_audit              # async (session, org_id, user_id, op, dataset, meeting_id=None)
from api.rbac.guards import require_org_admin, require_project_role  # FastAPI deps
```

`allowed_datasets(session, user, org_id, write=False) -> list[str]` returns
`ds_{project_id}` names + `ds_org_shared` per §4.4. Every cognee call site takes
datasets from it; the user never supplies a dataset name.

## Provided by meetings-capture

- Routers: `api/meetings/router.py` exposes `router` (prefix `/meetings`),
  webhooks at `POST /webhooks/livekit`.
- After assembling a transcript it calls (fire-and-forget task):
  `api.memory.pipeline.ingest_meeting(meeting_id: uuid.UUID) -> None`
  which reads `transcripts` + meeting metadata from the DB itself.
- Canonical transcript format stored in `transcripts.json_utterances`:
  `[{"speaker_identity": str, "speaker_name": str, "start": float, "end": float, "text": str}, ...]`
  and `transcripts.canonical_text` = lines of `[mm:ss] Name: text`.

## Provided by memory

- Router: `api/memory/router.py` exposes `router` (prefix `/memory`):
  `POST /memory/search`, `GET /memory/brief/{project_id}`,
  `POST /memory/reingest/{meeting_id}` (manager+), `DELETE /memory/project/{project_id}` (admin).
- `api/memory/pipeline.py: async def ingest_meeting(meeting_id)` — full §6 P3 order:
  set workspace(org) → add(doc, dataset=ds_{project}) → cognify once → extractor →
  `meetings.status = 'ready'`. Writes audit rows via `write_audit`.
- All cognee calls live in `api/memory/memory_service.py :: MemoryService` (§8).
- Doc header convention (§5.2), all sources forever:
  `[source: meeting] [project: {name}] [participants: {names}] [date: {iso}]`

## Router registration (fixed in api/main.py — do not edit main.py)

Each router module MUST expose a module-level `router = APIRouter(...)`:
`api.auth.router`, `api.rbac.router` (admin+audit endpoints), `api.meetings.router`,
`api.memory.router`.

## HTTP API surface consumed by web

Base `NEXT_PUBLIC_API_URL`. Auth: `POST /auth/jwt/login` (form: username,password) → bearer;
`POST /auth/register`. Everything else bearer-authed JSON:

- `GET /rbac/me` → { user, orgs: [{org_id, role}], projects: [{project_id, role}] }
- `GET/POST /meetings?project_id=` ; `POST /meetings/{id}/token` → { token, livekit_url }
- `GET /meetings/{id}/transcript` → utterances JSON above
- `GET /meetings/{id}/actions`, `PATCH /actions/{id}` (status)
- `POST /memory/search` { org_id, project_id?, query, search_type? } → { answer, citations[] }
- `GET /memory/brief/{project_id}` → markdown brief
- `GET /rbac/audit?org_id=` (admin/manager)

## Conventions

- IDs: UUIDv4 everywhere, `uuid.UUID` in Python, string in JSON.
- Meeting status enum: `scheduled | live | processing | ready` (§5.1).
- Roles: org: `admin|member`; project: `manager|member` (§4.1).
- Windows-native dev: no Unix-only assumptions (paths via pathlib, no uvloop).
- Python 3.11+, fully async SQLAlchemy 2.x, asyncpg driver.
