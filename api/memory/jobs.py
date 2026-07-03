"""Scheduled memory jobs (§8): monthly prune of superseded docs.

Registered by api.scheduler at startup. cognee 1.2.2 has no per-dataset prune
(cognee.prune wipes everything, no permission checks — never call it in prod);
supersede cleanup uses datasets.delete_data per superseded doc id, tracked in
sync_state. MVP: log-only placeholder so the schedule exists and is visible.
"""
from __future__ import annotations

import logging

from api.scheduler import scheduler

log = logging.getLogger(__name__)


async def prune_superseded_docs() -> None:
    log.info("monthly prune: scanning for superseded docs (MVP placeholder)")
    # P5: iterate sync_state entries "superseded:{dataset}:{data_id}" →
    # cognee.datasets.delete_data(dataset_id, data_id, user=org_user)


scheduler.add_job(
    prune_superseded_docs,
    trigger="cron",
    day=1,
    hour=3,
    minute=0,
    id="prune_superseded_docs",
    replace_existing=True,
)
