# meetgraph

**Self-hosted meetings with organizational memory.** Host video calls on your own
infrastructure, get speaker-attributed transcripts automatically, and query a
knowledge graph of every decision, action item, person, and topic — with
citations, RBAC, and a full audit trail. An AI presenter can even join your
meeting and present the project's memory out loud.

Built solo for the cognee hackathon (2026-07-03) on
[cognee](https://github.com/topoteretes/cognee) + [LiveKit](https://livekit.io) OSS.

## Why

Organizations run on meetings, but what meetings produce — decisions,
commitments, context — evaporates. Existing tools (Otter, Fireflies, Fathom)
are third-party bots bolted onto someone else's call: every conversation goes
to a vendor cloud, and speakers are *guessed* from mixed audio.

meetgraph owns the room instead:

- **Per-participant audio tracks** → speaker attribution is a fact, not an ML guess.
- **Your infrastructure** → video, transcripts, and the knowledge graph never
  leave your servers. The only external call in the data path is LLM inference
  (DeepSeek, swappable for self-hosted vLLM).
- **Organizational memory** → "what did we decide about X, who owns it, and
  why" answered with citations from the actual meeting.

## What works today (all live-verified)

| Capability | Detail |
|---|---|
| 🎥 Meetings | LiveKit rooms, RBAC-gated join, guest invites (time-boxed tokens) |
| 🎙️ Capture | Recorder bot writes per-track WAV; rooms auto-close & process when the last human leaves |
| 📝 Transcripts | faster-whisper per track + timestamp merge → speaker-attributed transcript, zero manual steps |
| 🧠 Memory | cognee knowledge graph per project (`workspace≈org`, `dataset≈project`), custom Meeting/Decision/ActionItem/Person ontology |
| 🔍 Ask | Cited Q&A over project memory; answers name the source meeting |
| 📋 Briefs | Pre-meeting brief generated from the graph, cached until memory changes |
| ✅ Actions | LLM-extracted action items with owners + deadlines, status syncs back into the graph append-only |
| 🤖 Presenter bot | Joins the call, screenshares a deck generated from project memory, narrates it (edge-tts), host controls next/stop |
| 🔐 RBAC | Org admin / project manager / member / guest; single resolver chokepoint; isolation tests gate CI |
| 🧾 Audit | Every memory operation (search/add/cognify/forget) logged and visible to admins |
| 🗑️ GDPR | One click destroys a project's memory entirely: graph dataset, recordings, transcripts, decks |
| 🛡️ Hardening | Rate limits on auth + LLM endpoints, prod config guards, backup scripts |

## Architecture

```
browser ⇄ LiveKit SFU (WebRTC)
              │
              ├─ webhooks ────────────────────────────► FastAPI
              │                                            │
              ├─ recorder bot: per-track WAV ──► faster-whisper (word timestamps)
              │                                            │
              └─ presenter bot ◄── deck (DeepSeek) ◄─┐     ▼
                 (Chromium screenshare + edge-tts)   │  transcript assembler
                                                     │  (merge tracks by time)
                                                     │     │
                                                     │     ▼
                                       cognee knowledge graph (single Postgres:
                                       relational + pgvector + graph, per-org
                                       tenant isolation, per-project datasets)
                                                     │
                                                     ▼
                                    RBAC-gated API: search / brief / actions
                                                     │
                                                     ▼
                                          Next.js dashboard + room UI
```

Stack: FastAPI (async) · Postgres 16+ w/ pgvector · cognee 1.2.2 · LiveKit OSS ·
faster-whisper · DeepSeek (`deepseek-chat`) + local fastembed embeddings ·
Next.js 16 + Tailwind v4 · Playwright + edge-tts for the presenter.

## Quickstart (Windows-native dev)

Prereqs: Python 3.11+, Node 20+, Postgres 16+ with pgvector
([Windows install notes](infra/pgvector-windows.md)), the
[LiveKit server binary](https://github.com/livekit/livekit/releases).

```powershell
# 1. Config — fill LLM_API_KEY (DeepSeek) and DB credentials
copy .env.template .env

# 2. Databases (once, as postgres superuser)
psql -U postgres -f infra\bootstrap.sql

# 3. API + workers
python -m venv .venv
.venv\Scripts\pip install -r api\requirements.txt
.venv\Scripts\python -m playwright install chromium   # presenter browser (once)
.venv\Scripts\alembic upgrade head
.venv\Scripts\python -m api.rbac.seed                 # demo users (password123)
.venv\Scripts\uvicorn api.main:app --port 8000

# 4. LiveKit (dev keys devkey/secret; config enables webhooks -> API)
livekit-server --config infra\livekit-dev.yaml --bind 127.0.0.1

# 5. Web
cd web; npm install; npm run dev
```

## Demo walkthrough

> 🎬 Recording the demo? The full scene-by-scene video script and the
> **how-we-use-cognee** technical walkthrough live in [docs/DEMO.md](docs/DEMO.md).

1. Sign in at `http://localhost:3000` as `manager@acme.test` / `password123`.
2. Create a meeting in **Apollo**, join it from two browser tabs, talk about
   a decision ("let's move the launch to the 17th"), assign someone a task.
3. Click **Present from memory** in the room — the AI presenter joins,
   screenshares a deck built from the project's knowledge graph, and narrates it.
4. Leave the meeting. Within seconds it flips to `processing`, then `ready` —
   speaker-attributed transcript, extracted action items with owners/deadlines.
5. Open **Ask** and type "what did we decide about the launch date?" — cited
   answer, naming the meeting it came from.
6. As `admin@acme.test`: check the **Audit** log, or nuke a project's memory
   entirely (GDPR path).

## Layout

```
api/        FastAPI: auth/ rbac/ meetings/ capture/ memory/ presenter/ connectors/
stt/        faster-whisper worker (compose service; in-process in dev)
web/        Next.js app (room UI, dashboard, ask, briefs, actions, audit)
infra/      livekit configs, docker-compose deploy stack, bootstrap.sql, backups
docs/       plan.md — the full build plan this repo implements
tests/      incl. cross-org / cross-project isolation tests (CI gate)
CONTRACTS.md  module boundaries (the repo was built by parallel agents)
```

## Roadmap

Directable presenter (voice/chat commands) → presenter drives the real app UI
with cursor → Zoom/Meet/Teams transcript ingestion → Notion/Slack connectors →
live captions + live memory → fully local inference (self-hosted vLLM serving
open-weight DeepSeek — zero external calls). Details in [docs/plan.md](docs/plan.md) §9.
