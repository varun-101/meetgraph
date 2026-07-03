# meetgraph — demo video script & cognee walkthrough

> 🎞️ A ready-made 37s animated intro (multi-voice narration + sound design)
> lives at [intro/meetgraph-intro-4k.webm](intro/meetgraph-intro-4k.webm)
> (3840×2160; a 720p cut is next to it). Rendered from
> [intro/intro.html](intro/intro.html) — open with `?scale=3` to replay at 4K,
> re-record via `record_4k.py`, rebuild audio via `build_audio.py`.
> Use it as the cold open before the live demo.

Target length: **5–6 minutes**. Every scene lists what's on screen, what you
say (verbatim, edit freely), and rough timing. Total speaking pace ~140 wpm.

---

## The 30-second pitch (memorize this)

> Organizations run on meetings, but what meetings produce — decisions,
> commitments, context — evaporates. Tools like Otter and Fireflies bolt a bot
> onto someone else's call, send your conversations to their cloud, and guess
> who spoke from mixed audio. meetgraph owns the room instead: self-hosted
> video, per-participant audio so speaker attribution is a fact, and every
> meeting distilled by **cognee** into a queryable knowledge graph — decisions,
> action items, people, topics — with citations, RBAC, and a full audit trail.
> Your meetings become organizational memory, on your servers.

---

## Pre-flight checklist (do BEFORE recording)

- [ ] Close spare browser tabs / heavy apps (STT needs ~2GB free RAM).
- [ ] Stack running: Postgres service, `livekit-server --config infra\livekit-dev.yaml --bind 127.0.0.1`, `uvicorn api.main:app --port 8000`, `npm run dev` in `web/`.
- [ ] `.env` has the DeepSeek key; whisper model already downloaded (run one meeting beforehand so nothing downloads on camera).
- [ ] At least one **already-processed meeting** exists in Apollo (status `ready`) so Ask/brief have memory to draw on even before your on-camera meeting finishes.
- [ ] Logins ready: `manager@acme.test` / `password123` (main), `member@acme.test` (second tab/incognito).
- [ ] Mic check — your voice is the demo data. Speak clearly; whisper `base` is good but not magic.
- [ ] OBS: capture the browser window at 1280×720+; system audio ON (the presenter bot talks!).

---

## Scene-by-scene script

### Scene 1 — The problem (0:00–0:30)
**Screen:** README hero or a title slide.
**Say:** the 30-second pitch above.

### Scene 2 — Host a real meeting (0:30–1:30)
**Screen:** Dashboard → Apollo → create meeting "Q3 planning" → Join. Open a
second tab as `member@acme.test`, join too. Cameras on.
**Say:**
> This is meetgraph's own meeting room — LiveKit, self-hosted, RBAC-gated:
> only project members can join, guests get time-boxed invite links.
> A hidden recorder bot is already capturing each of us on our own audio
> track — that's why attribution will be a fact, not a diarization guess.

**Then have a scripted 30-second conversation — this becomes your demo data:**
> MANAGER: "After the load test results, I'm moving the release to October 2nd."
> MEMBER: "Agreed. I'll finish the caching layer by September 20th so QA gets a full week."
> MANAGER: "And we decided to keep Postgres for the queue instead of adding Redis — one less system to operate."

### Scene 3 — The AI presenter (1:30–2:45) ← the wow moment
**Screen:** Click **Present from memory** in the floating pill. Wait for the
presenter tile (~20s — talk over it). Then type commands.
**Say while preparing:**
> Now the differentiator. I'm inviting an AI presenter into the call. It's
> reading this project's knowledge graph — built by cognee from previous
> meetings — and generating a slide deck about it, right now.

**When it starts narrating, let 1 slide play, then type:** `show the action tracker`
> It can also drive the real product UI — that's a live cursor touring our
> actual action tracker, narrating items from the database.

**Type:** `what did we decide about the launch date?`
> Ask it anything — it queries the graph, builds a new cited slide on the
> fly, and answers out loud.

**Type:** `mark the payment gateway task as done`
> And it can act: that's a real, audited write — made with MY permissions,
> not the bot's. Members can't close other people's tasks through it.

### Scene 4 — Leave, and memory builds itself (2:45–3:30)
**Screen:** Both tabs leave. Dashboard: status flips `live → processing →
ready` (~1–2 min — cut the wait in editing). Open the meeting page.
**Say:**
> We just leave. No "end recording", no export. Whisper transcribes each
> track, the assembler merges them on one timeline — and here's the
> transcript: every line attributed to its speaker, including what the AI
> presenter said. Then cognee takes over: the transcript becomes a document,
> `cognify` extracts a graph — decisions, action items with owners and
> deadlines, people, topics — and the action tracker fills itself.

### Scene 5 — Ask the memory (3:30–4:30) ← the cognee money shot
**Screen:** Ask page. Type: `when did we decide the release date and what is it now?`
**Say:**
> This is cognee's graph answering. Notice it's a *temporal* question — we
> cognify with time-awareness, so it knows the release date CHANGED and gives
> the latest decision, with when it happened. And every source is clickable —
> straight into the exact transcript. Click one. Answers with receipts.

**Screen:** Brief page.
> The pre-meeting brief: decisions, open actions, topics — generated from the
> graph, cached until the memory actually changes, so it costs nothing to
> re-open.

### Scene 6 — Governance (4:30–5:15)
**Screen:** Admin → Audit log; then dashboard sidebar → "Delete project memory…" (cancel the confirm!).
**Say:**
> For the orgs this is built for, governance is the product. Every memory
> operation — search, ingest, cognify, forget — is audited with who and what.
> Access is a single RBAC chokepoint: cognee dataset names only ever come
> from the permission resolver, and our CI gate is a cross-org isolation test.
> And the GDPR path is real: one admin action destroys a project's graph,
> recordings, and transcripts entirely.

### Scene 7 — Close (5:15–5:45)
**Screen:** Architecture diagram from the README.
**Say:**
> Everything you saw runs on one Postgres and one VPS-sized box. The only
> external call is LLM inference — DeepSeek today, self-hosted vLLM tomorrow,
> and then nothing leaves your infrastructure. meetgraph: host the meeting,
> capture it, remember it, answer from it — and now, let the memory present
> itself. Thanks!

---

## How we use cognee (walkthrough for judges)

| Feature you saw | cognee machinery behind it |
|---|---|
| Meeting → knowledge graph | `add(doc, dataset_name, user)` + `cognify(graph_model=…, temporal_cognify=True)` — one call per meeting, post-processing, async |
| Custom ontology | Pydantic `DataPoint` models ([api/memory/ontology.py](../api/memory/ontology.py)): Meeting, Decision, ActionItem, Person, Topic with typed edges — cognify's LLM extraction is *schema-constrained* to our domain |
| Entity merging across meetings | Deterministic doc header `[source: meeting] [project: X] [participants: …] [date: …]` gives cognify stable strings, so "Max Member" is ONE Person node across every meeting |
| Cited Q&A / presenter answers | `search(query, GRAPH_COMPLETION, datasets=…, include_references=True)` — graph-aware retrieval, Evidence block parsed into structured citations |
| Clickable citations | cognee names ingested docs `text_<md5(content)>`; we record `hash → meeting_id` at ingest, so every citation resolves to its transcript |
| Temporal answers | `temporal_cognify=True` + auto-routing time-flavored questions to `SearchType.TEMPORAL` (fallback to GRAPH_COMPLETION) |
| Hard tenant isolation | cognee multi-user mode (`ENABLE_BACKEND_ACCESS_CONTROL=true`): one cognee service-user per org, one dataset per project — cognee creates a **physical database per dataset**, so cross-project isolation isn't a WHERE clause |
| RBAC chokepoint | Dataset names passed to every cognee call come ONLY from `allowed_datasets()` ([api/rbac/resolver.py](../api/rbac/resolver.py)); users never supply them. CI gates on cross-org isolation tests |
| Single-Postgres self-host | `DB_PROVIDER=postgres`, `VECTOR_DB_PROVIDER=pgvector`, `GRAPH_DATABASE_PROVIDER=postgres` — relational + vectors (local fastembed) + graph in one operable database |
| Deletion / GDPR | `forget(dataset=…)` plus app-side purge of recordings/transcripts/decks; audited as `forget` |
| Version discipline | cognee pinned (1.2.2), every call behind one `MemoryService` class ([api/memory/memory_service.py](../api/memory/memory_service.py)) — the churn shield, the model-swap seam, and the cognee-Cloud seam in one place |

**One sentence for the submission form:** meetgraph uses cognee as its entire
memory layer — schema-constrained cognify over speaker-attributed transcripts
into a per-project, physically isolated knowledge graph on self-hosted
Postgres, queried through RBAC-gated temporal graph search with
transcript-linked citations, and presented back into live meetings by an AI
participant.

---

## Recording tips

- Record scenes **separately** and stitch — especially Scene 4 (cut the
  processing wait to ~3 seconds with a "moments later" cut).
- The presenter bot's voice comes through system audio — make sure OBS
  captures desktop audio, and pause your own narration while it speaks.
- If STT quality matters for the take, close Edge/Code first (RAM), or set
  `STT_MODEL=small` in `.env` for the recording session.
- Have the Ask question typed in a notepad to paste — no typos on camera.
- B-roll worth grabbing: the audit log filling up during the demo; the graph
  answering the Sept-15→16→17 supersession question.
