"""
Dead-letter queue read and retry operations. A DLQ retry is a deliberate,
authenticated backend action (POST, behind the same X-API-Key auth as
every other write) -- the dashboard never mutates job state directly, it
only ever calls this endpoint.
"""

import uuid
from datetime import datetime, timezone

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    DeadLetterJobAlreadyResolvedError,
    DeadLetterJobNotFoundError,
)
from app.core.states import JobStatus
from app.models.dead_letter_job import DeadLetterJob
from app.models.event import Event
from app.models.notification_job import NotificationJob
from app.schemas.ops import DeadLetterItem, DeadLetterListResponse, DeadLetterRetryResponse
from app.workers.dispatch import enqueue_notification_job

logger = structlog.get_logger(__name__)


async def list_dead_letter_jobs(
    db: AsyncSession, page: int, page_size: int
) -> DeadLetterListResponse:
    total = (
        await db.execute(select(func.count()).select_from(DeadLetterJob))
    ).scalar_one()

    # Joined through to Event as well, not just NotificationJob: the
    # dashboard needs the human-readable event_id string (e.g.
    # "evt_01HXYZ") to link to GET /api/v1/events/{event_id}, which looks
    # up by that string -- not the internal UUID primary key that
    # NotificationJob.event_id actually holds. Exposing the UUID under a
    # field named "event_id" would have been a silent, easy-to-miss bug:
    # every "view event" link in the dashboard would 404.
    query = (
        select(DeadLetterJob, NotificationJob, Event)
        .join(NotificationJob, DeadLetterJob.original_job_id == NotificationJob.id)
        .join(Event, NotificationJob.event_id == Event.id)
        .order_by(DeadLetterJob.failed_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    rows = (await db.execute(query)).all()

    items = [
        DeadLetterItem(
            id=str(dl.id),
            original_job_id=str(job.id),
            event_id=event.event_id,
            channel=job.channel.value,
            reason=dl.reason,
            attempt_count=job.attempt_count,
            failed_at=dl.failed_at,
            resolved_at=dl.resolved_at,
        )
        for dl, job, event in rows
    ]
    return DeadLetterListResponse(items=items, page=page, page_size=page_size, total=total)


async def retry_dead_letter_job(
    db: AsyncSession, dead_letter_id: str
) -> DeadLetterRetryResponse:
    """
    Resets a dead-lettered job back to QUEUED and re-enqueues it, with a
    fresh attempt budget.

    This deliberately does NOT go through app/core/states.py's
    JOB_TRANSITIONS table: DEAD_LETTERED has no outgoing transitions
    there by design, because it's meant to be a terminal state for
    *automatic* processing. This endpoint is the one sanctioned way out
    of it -- an explicit, authenticated human action (an operator clicked
    "retry" in the dashboard, or called this endpoint directly), not
    something the worker or recovery sweep would ever do on its own.
    Attempt bookkeeping resets to 0 rather than continuing from the
    exhausted count, since a human decided this deserves a fresh attempt
    budget under RetryPolicy.
    """
    try:
        dl_uuid = uuid.UUID(dead_letter_id)
    except ValueError as exc:
        raise DeadLetterJobNotFoundError(
            f"No dead-letter entry with id '{dead_letter_id}'."
        ) from exc

    dl_row = (
        await db.execute(select(DeadLetterJob).where(DeadLetterJob.id == dl_uuid))
    ).scalar_one_or_none()
    if dl_row is None:
        raise DeadLetterJobNotFoundError(
            f"No dead-letter entry with id '{dead_letter_id}'."
        )
    if dl_row.resolved_at is not None:
        raise DeadLetterJobAlreadyResolvedError(
            f"Dead-letter entry '{dead_letter_id}' was already retried at "
            f"{dl_row.resolved_at.isoformat()}."
        )

    job = (
        await db.execute(
            select(NotificationJob).where(NotificationJob.id == dl_row.original_job_id)
        )
    ).scalar_one_or_none()
    if job is None:
        raise DeadLetterJobNotFoundError(
            f"The original job for dead-letter entry '{dead_letter_id}' no longer exists."
        )

    event = (await db.execute(select(Event).where(Event.id == job.event_id))).scalar_one()

    job.status = JobStatus.QUEUED
    job.attempt_count = 0
    job.last_error = None
    job.scheduled_at = None
    job.claimed_at = None
    job.lease_expires_at = None

    dl_row.resolved_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(job)

    try:
        enqueue_notification_job(job.id, job.channel)
    except Exception:  # noqa: BLE001 -- broker hiccup must not fail a request whose DB update already committed
        logger.error("dlq_retry_enqueue_failed", job_id=str(job.id))

    return DeadLetterRetryResponse(
        job_id=str(job.id),
        event_id=event.event_id,
        channel=job.channel.value,
        status=job.status.value,
    )
