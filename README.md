# meetgraph — Meeting Intelligence Platform

Self-hosted meetings (LiveKit) + organizational memory (cognee). Host the call,
capture per-participant audio, get speaker-attributed transcripts, and query a
knowledge graph of decisions, action items, people, and topics — all on your
own infrastructure. See [docs/plan.md](docs/plan.md) for the full plan and
[CONTRACTS.md](CONTRACTS.md) for module boundaries.

## Dev quickstart (Windows native)

Prereqs: Python 3.11+, Node 20+, Postgres 16+ with pgvector, LiveKit server binary.

```powershell
# 1. Config
copy .env.template .env    # fill LLM_API_KEY (DeepSeek), DB credentials

# 2. Databases (once): create `meetgraph` and `meetgraph_cognee`, enable pgvector
#    See infra/bootstrap.sql

# 3. API + workers
python -m venv .venv
.venv\Scripts\pip install -r api\requirements.txt
.venv\Scripts\alembic upgrade head
.venv\Scripts\uvicorn api.main:app --reload --port 8000

# 4. LiveKit (dev keys devkey/secret; config enables webhooks -> API)
livekit-server --config infra\livekit-dev.yaml --bind 127.0.0.1

# 5. Web
cd web; npm install; npm run dev
```

## Layout

```
api/        FastAPI: auth/ rbac/ meetings/ capture/ memory/ connectors/
stt/        faster-whisper worker
web/        Next.js app (room UI, dashboard, search)
infra/      livekit.yaml, docker-compose (deploy), bootstrap.sql, backups
docs/       plan.md
tests/      incl. cross-org / cross-project isolation tests (CI gate)
```
