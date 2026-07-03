"""In-process APScheduler (§3.2). Jobs: monthly superseded-doc prune (§8),
weekly digest (P5 option). Orchestrator-owned shell; jobs self-register via
register_job() from their own modules at import time in lifespan."""
from apscheduler.schedulers.asyncio import AsyncIOScheduler

scheduler = AsyncIOScheduler()


async def start_scheduler() -> None:
    # Import modules that register jobs (kept lazy to avoid import cycles)
    try:
        from api.memory import jobs as _memory_jobs  # noqa: F401
    except ImportError:
        pass
    if not scheduler.running:
        scheduler.start()


async def stop_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
