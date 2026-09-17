"""
Crash recovery, run periodically via Celery Beat (see
app/workers/celery_app.py's beat_schedule).

Handles two distinct failure modes:

1. Worker crashed mid-processing. A job stuck in PROCESSING with an
   expired lease_expires_at is assumed abandoned and is reset to QUEUED
   so a healthy worker can pick it up. No distributed lock needed here --
   the same FOR UPDATE SKIP LOCKED pattern used for normal job claiming
   makes it safe for overlapping recovery sweeps to run concurrently.

2. The documented failure window from event creation
   (app/services/event_service.py): the DB transaction committed a job as
   QUEUED, but the subsequent Celery publish failed (e.g. Redis was
   briefly unreachable) or was never attempted due to a crash between the
   two. Such a job has no claimed_at and sits QUEUED indefinitely with no
   task in flight. Anything QUEUED, unclaimed, and older than
   STALE_QUEUED_THRESHOLD_SECONDS gets re-published.

This is what makes "at-least-once" true in practice rather than only in
the enqueue path -- Pulse does not claim exactly-once delivery anywhere.
"""

import asyncio
from datetime import datetime, timedelta, timezone

import structlog
from sqlalchemy import select

from app.core.states import JobStatus, NotificationChannel
from app.db.session import AsyncSessionLocal, engine
from app.models.notification_job import NotificationJob
from app.workers.celery_app import celery_app
from app.workers.dispatch import enqueue_notification_job

logger = structlog.get_logger(__name__)

STALE_QUEUED_THRESHOLD_SECONDS = 60


@celery_app.task(name="app.workers.recovery.recover_stale_jobs")
def recover_stale_jobs() -> None:
    asyncio.run(_run_and_dispose())


async def _run_and_dispose() -> None:
    # Same cross-event-loop fix as app/workers/tasks.py: this task also
    # gets a fresh event loop per Beat-scheduled run via asyncio.run, so
    # the shared engine's connection pool must be disposed before the
    # loop closes -- otherwise the next run (or a worker task run in the
    # same process) can try to reuse a connection tied to this now-dead
    # loop.
    try:
        await _recover_stale_jobs()
    finally:
        await engine.dispose()


async def _recover_stale_jobs() -> None:
    recovered: list[tuple[object, NotificationChannel]] = []
    now = datetime.now(timezone.utc)

    async with AsyncSessionLocal() as session:
        async with session.begin():
            stale_processing = (
                (
                    await session.execute(
                        select(NotificationJob)
                        .where(NotificationJob.status == JobStatus.PROCESSING)
                        .where(NotificationJob.lease_expires_at < now)
                        .with_for_update(skip_locked=True)
                    )
                )
                .scalars()
                .all()
            )
            for job in stale_processing:
                job.status = JobStatus.QUEUED
                job.claimed_at = None
                job.lease_expires_at = None
                recovered.append((job.id, job.channel))

            never_enqueued = (
                (
                    await session.execute(
                        select(NotificationJob)
                        .where(NotificationJob.status == JobStatus.QUEUED)
                        .where(NotificationJob.claimed_at.is_(None))
                        .where(
                            NotificationJob.created_at
                            < now - timedelta(seconds=STALE_QUEUED_THRESHOLD_SECONDS)
                        )
                        .with_for_update(skip_locked=True)
                    )
                )
                .scalars()
                .all()
            )
            for job in never_enqueued:
                recovered.append((job.id, job.channel))

    for job_id, channel in recovered:
        logger.warning("job_recovered", job_id=str(job_id), channel=channel.value)
        try:
            enqueue_notification_job(job_id, channel)
        except Exception:  # noqa: BLE001 -- one broker hiccup must not abort the whole sweep
            logger.error(
                "job_recovery_enqueue_failed", job_id=str(job_id), channel=channel.value
            )
