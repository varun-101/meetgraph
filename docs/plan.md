# plan.md — Meeting Intelligence Platform (codename: `meetgraph`)

| Field | Value |
|---|---|
| Version | 1.1 — decisions locked |
| Date | 2026-07-03 |
| Owner | Varun Chandwani |
| Build model | Solo dev, ~12 weeks, phased with gates |
| Stack baseline | FastAPI · Postgres (single instance) · Next.js · native dev, Docker at deploy (P5) |
| v1.1 changes | LLM → DeepSeek (+ local fastembed embeddings) · no-Docker dev path (§3.3) · summary added (§0) |

---

## 0. Summary — what we're building and why

**What:** A self-hosted, one-stop meeting platform with organizational memory. Teams host video meetings on their own infrastructure (LiveKit); every meeting is auto-transcribed with exact speaker attribution and distilled into a queryable knowledge graph (cognee) of decisions, action items, people, projects, and topics — with role-based control over who can query, write, or delete that memory.

**Problem it solves:** Organizations run on meetings, but what meetings produce — decisions, commitments, context — evaporates. Existing tools (Otter, Fireflies, Fathom) are third-party bots bolted onto someone else's call: they require sending every conversation to a vendor cloud, and they guess who spoke from mixed audio. Privacy-sensitive orgs can't use them at all.

**How it wins:** Own the room → per-participant audio → speaker attribution as fact, not inference. Own the memory → transcripts and the graph stay on customer infrastructure. Result: "what did we decide about X, who owns it, and why" answered with citations, on servers you control.

---

## 1. Locked decisions

| # | Decision | Choice | Consequence |
|---|---|---|---|
| D1 | Video layer | LiveKit, self-hosted OSS | We own capture. Per-track audio → speaker-perfect transcripts with zero diarization. Ops burden (TURN, UDP, recording) accepted. |
| D2 | Memory runtime | cognee, self-hosted OSS | Meeting data never leaves our infra — this is the product wedge. cognee Cloud stays available behind an env-var seam (`COGNEE_BASE_URL` + `COGNEE_API_KEY`), never hard-wired. |
| D3 | Permissions | Roles + per-project scoping | RBAC in app layer; cognee `workspace = org`, `dataset = project` is the isolation mechanism it maps onto. |
| D4 | LLM (v1.1) | DeepSeek API (`deepseek-chat`) | Low token cost; OpenAI-compatible. No embeddings API → pair with local fastembed. Open weights = future fully-local inference path (§9.7). |

Deferred by explicit scope decision: Zoom/Meet/Teams ingestion, Notion/Slack connectors (code already written — see §9), calendar sync, billing, mobile.

---

## 2. Positioning

One-stop platform: host the meeting, capture it, remember it, answer from it. Competitors (Otter, Fireflies, Fathom) are SaaS recorders bolted onto someone else's call — they get mixed audio and guess who spoke. We own the room, so we get:

- Per-participant audio tracks → speaker attribution is a fact, not an ML guess.
- Live transcript access with no third-party API limits or bot-joins.
- Data sovereignty: video, transcripts, and the knowledge graph run on customer-controlled infrastructure. The sole external call in the data path is LLM inference (DeepSeek API) — removable later via self-hosted open weights (§9.7).

Target buyer: ops teams at privacy-sensitive orgs (legal, finance, defense-adjacent, EU) for whom "your meetings on our servers" is disqualifying.

---

## 3. Architecture

### 3.1 Data flow

```
browser ⇄ LiveKit SFU (WebRTC)
              │
              ├─ webhooks (room_started / room_finished) ──────────► FastAPI
              │
              └─ recorder bot (dev) / Egress (deploy):
                 per-track audio files ──► STT worker (faster-whisper)
                                                        │
                                                        ▼
                                          transcript assembler
                                     (merge tracks by word timestamps)
                                                        │
                                                        ▼
                              cognee  [workspace = org] [dataset = project]
                                add() → cognify() → knowledge graph
                                                        │
                                                        ▼
                            FastAPI query API (RBAC-gated search/brief/actions)
                                                        │
                                                        ▼
                                        Next.js dashboard + room UI
```

### 3.2 Components

| Component | Tech | Dev → deploy | Notes |
|---|---|---|---|
| Web app | Next.js 14+, `@livekit/components-react`, Tailwind | `next dev` → container | Room UI, dashboard, admin/RBAC, search |
| API | FastAPI (async), fastapi-users (JWT auth) | `uvicorn` in venv → container | Auth, RBAC resolver, token minting, orchestration, cognee SDK host |
| SFU | LiveKit server OSS | single Go binary `--dev` → container | Embedded TURN enabled at deploy |
| Coordination | Redis | deploy only | Required only by Egress — absent from the native dev stack |
| Recording | Recorder bot (dev) / LiveKit Egress (deploy) | Python process → container | Bot subscribes to tracks, writes per-track WAV; Egress swaps in at P5 |
| STT worker | Python + faster-whisper (int8) | worker process → container | Post-meeting batch (MVP); live captions = stretch |
| DB | Postgres 16 + pgvector | `apt install` → container | App schema + all four cognee backends (§8) |
| Memory | cognee (pip, inside `api`/worker) | library | Not a separate service in MVP |
| Scheduler | APScheduler in `api` | in-process | Digests, prune jobs; upgrade to ARQ only if needed |

### 3.3 Dev without Docker (native stack) — v1.1

Docker is deferred to deploy (P5). The full dev loop runs natively on WSL2 Ubuntu:

| Compose service | Native substitute |
|---|---|
| `db` | `apt install postgresql-16 postgresql-16-pgvector` |
| `redis` | Dropped — only Egress needed it |
| `livekit` | `livekit-server` single Go binary with `--dev` flag (predefined keys, localhost bind) |
| `egress` | Recorder-bot participant (livekit Python SDK) subscribing to audio tracks, writing per-track WAV |
| `api` / `stt` | `uvicorn` + worker processes in one venv |
| `web` | `next dev` |

Rules: `.env.template` is shared between native and compose so config never forks; the P5 gate includes a green full run under compose before VPS deploy. WSL2 caveat: `localhost` forwarding covers browser-on-Windows → WSL2, but testing from a phone on LAN needs `netsh portproxy` on Windows — check winnat reserved port ranges first (known quirk).

---

## 4. RBAC design (D3)

### 4.1 Roles

| Role | Scope | Grant path |
|---|---|---|
| Org admin | Org | `org_members.role = admin` |
| Project manager | Project | `project_members.role = manager` |
| Member | Project | `project_members.role = member` |
| Guest | Single meeting | Row in `meeting_guests`, expires with meeting |

### 4.2 Permission matrix

| Capability | Admin | Manager | Member | Guest |
|---|---|---|---|---|
| Create/delete projects | ✓ | — | — | — |
| Manage org users, connector config | ✓ | — | — | — |
| Create/host meetings in project | ✓ | ✓ | — | — |
| Attend meetings | ✓ | ✓ | ✓ | ✓ (invited room only) |
| Query project memory (search/brief) | ✓ | ✓ | ✓ | — |
| Write memory (re-ingest, correct decisions, edit action items) | ✓ | ✓ | — | — |
| Delete/`forget()` project dataset | ✓ | — | — | — |
| View audit log | ✓ | ✓ (own project) | — | — |

### 4.3 Mapping onto cognee

- Tenancy: `set_workspace(org_id)` on **every** request that touches cognee. No exceptions — this is the hard isolation boundary.
- Scoping: one dataset per project, name `ds_{project_id}`, plus `ds_org_shared` (admin-writable, org-readable).
- Reads: `search()` receives only dataset names emitted by the resolver below. The user never supplies a dataset name directly.
- Writes: `add()`/`cognify()` gated to manager+; `forget()` gated to admin.
- Guests: their utterances are captured into the meeting transcript (they were in the room), but they hold zero memory-query capability.

### 4.4 Enforcement — single chokepoint

```python
async def allowed_datasets(user: User, org_id: str, write: bool = False) -> list[str]:
    rows = await db.fetch(
        """SELECT project_id, role FROM project_members
           WHERE user_id = $1 AND org_id = $2""", user.id, org_id)
    if write:
        return [f"ds_{r['project_id']}" for r in rows if r["role"] in ("manager",)] \
               + (["ds_org_shared"] if user.is_org_admin(org_id) else [])
    return [f"ds_{r['project_id']}" for r in rows] + ["ds_org_shared"]
```

Rules: every cognee call site takes datasets from this function only; CI includes a cross-org and cross-project isolation test (user A must get zero results from project B); every memory op writes to `audit_log`.

### 4.5 Audit log

`audit_log(id, org_id, user_id, op ∈ {search, add, cognify, forget, export}, dataset, meeting_id?, ts)` — surfaced in admin UI (Phase 5). Aligns with cognee's traceability/OTEL support for later deep tracing.

---

## 5. Data model

### 5.1 App schema (Postgres)

| Table | Key columns |
|---|---|
| `users` | id, email, name, hashed_pw |
| `orgs` | id, name |
| `org_members` | org_id, user_id, role |
| `projects` | id, org_id, name |
| `project_members` | project_id, user_id, role |
| `meetings` | id, project_id, title, livekit_room, status ∈ {scheduled, live, processing, ready}, started_at, ended_at |
| `meeting_guests` | meeting_id, email, token_hash, expires_at |
| `recordings` | meeting_id, participant_identity, file_path, duration |
| `transcripts` | meeting_id, canonical_text, json_utterances |
| `action_items` | id, meeting_id, project_id, text, owner_user_id, deadline, status |
| `audit_log` | see §4.5 |
| `sync_state` | key, value — reserved for §9 connectors |

`action_items` status lives here for fast UI mutation; status changes sync into the graph via `add()` (append-only status doc), not by mutating graph nodes.

### 5.2 cognee ontology (Pydantic, passed to `cognify()`)

| Node | Fields | Edges |
|---|---|---|
| Meeting | id, title, date, project_id | → Decision, ActionItem, Topic |
| Decision | text, confidence, date | → Person (made_by), Project (affects) |
| ActionItem | text, deadline, status | → Person (owner), Meeting (from) |
| Person | name, role, team | → Decision, ActionItem |
| Project | name, status | → Meeting, Decision |
| Topic | name, keywords | ↔ Meeting |

Doc header convention (all sources, forever): `[source: meeting] [project: {name}] [participants: {names}] [date: {iso}]` — shared Person/Project/Topic strings are what let `cognify()` merge entities across meetings and, later, Notion/Slack docs.

---

## 6. Phased build (gates are hard — no phase starts before the prior gate passes)

| Phase | Weeks | Deliverables | Gate |
|---|---|---|---|
| 0 — Foundations | 1 | Repo + native dev stack (§3.3: apt Postgres+pgvector, `livekit-server --dev`, venv, `next dev`); fastapi-users auth; org/project/RBAC tables + `allowed_datasets` resolver; CI with isolation tests | Two users in two orgs; cross-org isolation test green |
| 1 — Meeting core | 2–3 | LiveKit dev config; server-side token minting (grants derived from RBAC); Next.js room UI; room lifecycle webhooks → `meetings.status` | Two browsers complete a call locally; join blocked for non-members |
| 2 — Capture | 4–5 | Recorder bot joins on `room_started`, writes per-track WAV; STT worker: faster-whisper with word timestamps per file; assembler merges tracks by timestamp → speaker-attributed canonical transcript; stored in `transcripts` | Ending a meeting produces a correct speaker-attributed transcript with zero manual steps |
| 3 — Memory core | 6–7 | cognee wired (workspace/org, dataset/project, ontology); post-meeting `add()` + single `cognify()`; `search()` endpoints: Q&A with citations, pre-meeting brief; action-item extractor (LLM structured-output pass) → `action_items` + graph | "What did we decide about X?" returns a cited answer from a real recorded meeting |
| 4 — Product surfaces | 8–9 | Dashboard: meeting list, transcript viewer (click utterance → audio seek), brief page, action tracker with status sync, search UI | Full loop demo: schedule → meet → transcript → query → action tracked, all in UI |
| 5 — Hardening + wedge | 10–12 | Admin audit-log UI; `forget()` + recording deletion (GDPR path); rate limits; backups (pg_dump + recordings); containerize — Docker Compose parity run, optional Egress swap-in; VPS deploy (TLS, TURN verified from mobile network); ship ONE differentiator: contradiction detector **or** weekly exec digest | An external user completes meeting + query unassisted on the deployed instance |

### Phase detail notes

- **P1 token minting**: API endpoint checks `project_members` → mints LiveKit access token (JWT: room grant, identity = user_id, metadata = {role}). This is where RBAC meets WebRTC; guests get single-room, time-boxed tokens.
- **P2 live captions**: explicitly a stretch goal via LiveKit Agents, not on the critical path. Post-meeting batch STT is reliable on CPU (`small`/int8); concurrent live STT for N tracks is not, without GPU. Do not let live captions block the P2 gate.
- **P3 pipeline order**: assemble transcript → `set_workspace(org)` → `add(doc, dataset_name=f"ds_{project_id}")` → `cognify()` once → extractor pass → mark `meetings.status = ready`.

---

## 7. LiveKit implementation notes (D1)

| Item | Setting |
|---|---|
| Dev mode | `livekit-server --dev` — predefined API key/secret, localhost bind; production `livekit.yaml` lands at P5 |
| Ports | 7880 ws/http, 7881 TCP fallback, UDP 50000–60000 (opened on VPS firewall at deploy) |
| TURN | Embedded TURN + TLS on 443 at deploy — required for corporate-NAT attendees; verify from a mobile network before P5 sign-off |
| Recording | Dev: recorder-bot participant (Python SDK) → per-track WAV. Deploy: Track egress (audio only, per participant), disk volume shared with STT |
| Webhooks | `room_started` (spawn recorder bot), `room_finished` (trigger capture pipeline), `participant_joined` |
| Redis | Only once Egress is enabled (P5) |
| Keys | Dev keys from `--dev`; deploy key/secret server-side only, never shipped to browser |

---

## 8. cognee implementation notes (D2, D4)

Single-Postgres configuration — one database to operate:

```env
DB_PROVIDER=postgres
VECTOR_DB_PROVIDER=pgvector
GRAPH_DATABASE_PROVIDER=postgres
CACHE_BACKEND=postgres

LLM_PROVIDER=custom                      # OpenAI-compatible endpoint
LLM_MODEL=deepseek/deepseek-chat
LLM_ENDPOINT=https://api.deepseek.com/v1
LLM_API_KEY=sk-...

EMBEDDING_PROVIDER=fastembed             # DeepSeek has no embeddings API — embed locally
EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
EMBEDDING_DIMENSIONS=384
```

Conventions:

- Pin the cognee version; it moves fast. Upgrades happen deliberately, in a branch, with the isolation tests green.
- All cognee calls live behind one `MemoryService` class — this is simultaneously the version-churn shield, the model-swap seam, and the cognee Cloud seam (swap = set `COGNEE_BASE_URL` + `COGNEE_API_KEY`, per org if a customer ever wants managed).
- DeepSeek notes (v1.1): `deepseek-chat` is OpenAI-compatible — JSON mode and function calling work for the action-item extractor. If cognify entity-extraction quality dips, the `MemoryService` seam makes the model swap a one-line change. Verify the exact `LLM_PROVIDER`/embedding strings against the pinned cognee version's `.env.template`.
- Sovereignty note (v1.1): `cognify()`/`search()` send transcript text to the DeepSeek API. DeepSeek weights are open — a self-hosted vLLM endpoint later makes inference fully local via an `LLM_ENDPOINT` swap alone (§9.7).
- Updated content (edited transcript, re-run extraction) is re-added as a superseding doc with the same header; a scheduled prune job removes superseded docs monthly.
- Live session memory (`remember()` per utterance, `improve()` at close) is deferred until live captions exist — batch path first.

---

## 9. Deferred roadmap (ordered)

| # | Item | Notes |
|---|---|---|
| 1 | Zoom / Meet / Teams ingestion | Webhook + transcript-file ingest into the same pipeline at the assembler step; "other sites" become just another capture source |
| 2 | Notion + Slack connectors | Code already written (2026-07-03 session): fetch → normalize → hash-dedupe → `add()`; drop into `api/connectors/`, map channels/pages → project datasets, wire `sync_state` |
| 3 | Calendar integration | Auto-create meetings, auto-send pre-briefs T-30min |
| 4 | Second differentiator | Whichever of contradiction detector / exec digest wasn't shipped in P5; then dependency radar, expertise router |
| 5 | Billing | Per-org subscription; COGS note: cognee Cloud at $5/workspace is the managed alternative if self-host ops ever dominate |
| 6 | Mobile | LiveKit has native SDKs; web-first until then |
| 7 | Self-hosted LLM inference | vLLM serving open-weight DeepSeek on a GPU box → zero external calls; completes the sovereignty story |

---

## 10. Cost estimate (MVP, monthly)

| Item | Cost |
|---|---|
| VPS 8 GB / 4 vCPU (Hetzner CPX/DO) | ~$25–48 |
| LLM tokens — DeepSeek (cognify + search + extraction, dev volume) | ~$2–15 (a fraction of frontier-model rates) |
| Embeddings | $0 (fastembed, local CPU) |
| STT | $0 (self-hosted faster-whisper, CPU) |
| Domain + TLS | ~$1 (Let's Encrypt free) |
| **Total** | **< $75/mo** |

---

## 11. Risks

| Risk | Mitigation |
|---|---|
| WebRTC ops (NAT/TURN failures) | Embedded TURN + TCP fallback; test from mobile + corporate networks early at deploy, not after |
| STT quality (accents, jargon) | Per-track capture removes crosstalk (the worst offender); model-size upgrade path; transcript edit UI in P4 |
| cognify cost/latency on long meetings | Chunk transcript by agenda segments; cognify runs async post-meeting, UI shows `processing` state |
| DeepSeek extraction quality on cognify | `MemoryService` seam = one-line model swap; spot-check graph output as part of the P3 gate |
| Native-dev / Docker-prod drift | Shared `.env.template`; P5 gate requires a green full run under compose before VPS deploy |
| cognee API churn | Version pin + `MemoryService` wrapper (§8) |
| RBAC leak | Single resolver chokepoint (§4.4) + isolation tests in CI as a gate condition |
| Duplicate docs in graph | Supersede convention + monthly prune (§8) |
| Solo scope creep | Gates are hard; §9 is a contract — nothing in it enters scope before P5 passes |

---

## 12. Repo layout

```
meetgraph/
  .env.template        shared by native dev and compose (P5)
  docker-compose.yml   lands at P5
  api/
    auth/          fastapi-users setup
    rbac/          resolver, permission deps, audit
    meetings/      rooms, tokens, webhooks, lifecycle
    capture/       recorder bot, stt dispatch, assembler
    memory/        MemoryService, ontology.py, extractor
    connectors/    (empty until §9.2 — notion.py, slack.py land here)
  stt/             faster-whisper worker
  web/             Next.js app
  infra/           livekit.yaml, egress.yaml, deploy scripts, backups
  docs/
    plan.md        this file
```

## 13. Definition of done (MVP)

1. Meeting hosted on own domain, works through corporate NAT.
2. Transcript is speaker-attributed automatically, no manual step.
3. Cited Q&A over any project's meeting history, RBAC-enforced.
4. Action items extracted, tracked, and status-synced to the graph.
5. Admin can audit every memory operation and delete a project's memory entirely.
6. Deploy target runs from `docker compose up` on one VPS (dev runs native); the only external call in the data path is the DeepSeek API — removable via §9.7.
