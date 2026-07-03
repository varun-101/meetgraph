"""meetgraph API entrypoint. Orchestrator-owned — routers register here and
build agents must NOT edit this file (see CONTRACTS.md)."""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Scheduler (APScheduler) starts here; jobs registered in api.memory.pipeline
    from api.scheduler import start_scheduler, stop_scheduler

    await start_scheduler()
    yield
    await stop_scheduler()


app = FastAPI(title="meetgraph", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.web_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Router registration (contract: each module exposes `router`) ---
from api.auth.router import router as auth_router          # noqa: E402
from api.rbac.router import router as rbac_router          # noqa: E402
from api.meetings.router import router as meetings_router  # noqa: E402
from api.meetings.webhooks import router as webhooks_router  # noqa: E402
from api.memory.router import router as memory_router      # noqa: E402
from api.presenter.router import router as presenter_router  # noqa: E402

app.include_router(auth_router)
app.include_router(rbac_router)
app.include_router(meetings_router)
app.include_router(webhooks_router)
app.include_router(memory_router)
app.include_router(presenter_router)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "env": settings.app_env}
