"""
The worker's job-processing task.

Structured as three short, separate database transactions around one
provider call that holds no transaction open at all:

    BEGIN; claim job (FOR UPDATE SKIP LOCKED), attempt_count += 1 COMMIT
    <-- provider.send() happens here, no open transaction -->
    BEGIN; record delivery, transition job, maybe schedule retry COMMIT
    (separately) refresh the parent event's aggregate status

This is deliberate: a slow or hanging provider call must never hold a
Postgres row lock, and the claim step's SKIP LOCKED is what makes
concurrent claims of the same job safe -- a second worker (or a
redelivered Celery message for the exact same attempt) simply finds the
row already locked or already moved out of QUEUED/RETRYING, and returns
without side effects. That's also what makes duplicate task execution
safe: idempotency comes from the database job state, not from Celery's
task ID.
"""

import asyncio
import uuid
from datetime import datetime, timedelta, timezone

import structlog
from celery import Task
from sqlalchemy import select
from sqlalchemy.exc import NoResultFound

from app.core.retry_policy import get_retry_policy
from app.core.states import (
    DeliveryStatus,
    JobStatus,
    NotificationChannel,
    assert_job_transition,
)
from app.core import metrics
from app.core.rate_limiter import get_rate_limiter
from app.db.session import AsyncSessionLocal, engine
from app.models.dead_letter_job import DeadLetterJob
from app.models.notification_delivery import NotificationDelivery
from app.models.notification_job import NotificationJob
from app.providers.registry import get_provider
from app.workers.celery_app import celery_app
from app.workers.dispatch import enqueue_notification_job
from app.workers.event_aggregation import refresh_event_status

logger = structlog.get_logger(__name__)

# Long enough for a slow mock/real provider call to complete, short enough
# that a crashed worker's job doesn't sit stuck for long before the
# recovery sweep (app/workers/recovery.py) reclaims it.
LEASE_DURATION_SECONDS = 300


@celery_app.task(name="app.workers.tasks.process_notification_job", bind=True)
def process_notification_job(self: Task, job_id: str, channel: str) -> None:
    """
    Celery's worker is a sync (prefork) process, not an asyncio runtime,
    so each task invocation runs its own event loop via asyncio.run rather
    than trying to share one across tasks.

    `channel` is passed explicitly (not re-derived from the DB) so the
    rate-limit check in _process_notification_job can run before opening
    any database transaction at all -- checking Redis while holding a
    Postgres row lock would be exactly the "external call inside an open
    transaction" problem this module's docstring warns against.
    """
    asyncio.run(_run_and_dispose(uuid.UUID(job_id), NotificationChannel(channel)))


async def _run_and_dispose(job_id: uuid.UUID, channel: NotificationChannel) -> None:
    """
    Wraps the real task body so the shared async engine's connection pool
    (app/db/session.py's module-level `engine`) is disposed at the end of
    THIS event loop, before it closes.

    Bug this fixes: `engine` is a singleton created once at import time,
    but each Celery task here gets a brand-new event loop via
    asyncio.run(). A connection checked into the pool during one task's
    loop is not valid in the next task's (different) loop -- asyncpg ties
    connections to the loop that created them. Without disposal, the
    second task to run in a given worker process would intermittently
    fail with a cross-event-loop error from asyncpg. Disposing here means
    every task starts its DB work with a clean pool, and the next task's
    asyncio.run() lazily creates fresh connections correctly scoped to
    its own loop.

    The rate limiter's Redis client has the exact same problem (it's also
    a lazily-created, process-wide singleton) and gets the same fix.
    """
    try:
        await _process_notification_job(job_id, channel)
    finally:
        await engine.dispose()
        await get_rate_limiter().aclose()


RATE_LIMIT_RETRY_DELAY_SECONDS = 2.0


async def _process_notification_job(job_id: uuid.UUID, channel: NotificationChannel) -> None:
    limiter = get_rate_limiter()
    if not await limiter.allow(channel):
        # Rate limiting is not a provider failure: it must not touch
        # attempt_count, RetryPolicy, or create a delivery record. The
        # job is left exactly as it was (QUEUED or RETRYING) and the same
        # task is rescheduled after a short, fixed delay -- deliberately
        # NOT the RetryPolicy backoff, and deliberately not immediate
        # (which would hot-loop against an exhausted rate limit).
        metrics.rate_limit_denied_total.labels(channel=channel.value).inc()
        logger.info("job_rate_limited", job_id=str(job_id), channel=channel.value)
        try:
            enqueue_notification_job(
                job_id, channel, countdown=RATE_LIMIT_RETRY_DELAY_SECONDS
            )
        except Exception:  # noqa: BLE001 -- broker hiccup must not crash the worker
            logger.error(
                "rate_limit_reenqueue_failed", job_id=str(job_id), channel=channel.value
            )
        return

    claim = await _claim_job(job_id)
    if claim is None:
        logger.info("job_claim_skipped", job_id=str(job_id))
        return

    recipient, attempt_number = claim
    metrics.notifications_processed_total.labels(channel=channel.value).inc()
    provider = get_provider(channel)

    start = datetime.now(timezone.utc)
    error_message: str | None
    provider_message_id: str | None
    try:
        result = provider.send(recipient=recipient, job_id=str(job_id))
    except Exception as exc:  # noqa: BLE001 -- provider boundary: any failure must be recorded, never swallowed
        success = False
        provider_message_id = None
        error_message = f"provider raised: {exc}"
    else:
        success = result.success
        provider_message_id = result.provider_message_id
        error_message = result.error_message
    duration_seconds = (datetime.now(timezone.utc) - start).total_seconds()

    metrics.notification_processing_duration_seconds.labels(
        channel=channel.value, provider=provider.name
    ).observe(duration_seconds)

    logger.info(
        "job_processing_attempt",
        job_id=str(job_id),
        channel=channel.value,
        attempt=attempt_number,
        provider=provider.name,
        status="delivered" if success else "failed",
        duration_ms=int(duration_seconds * 1000),
        error=error_message,
    )

    await _record_outcome(
        job_id=job_id,
        channel=channel,
        provider_name=provider.name,
        success=success,
        provider_message_id=provider_message_id,
        error_message=error_message,
    )


async def _claim_job(job_id: uuid.UUID) -> tuple[str, int] | None:
    async with AsyncSessionLocal() as session:
        async with session.begin():
            result = await session.execute(
                select(NotificationJob)
                .where(NotificationJob.id == job_id)
                .where(NotificationJob.status.in_([JobStatus.QUEUED, JobStatus.RETRYING]))
                .with_for_update(skip_locked=True)
            )
            job = result.scalar_one_or_none()
            if job is None:
                return None

            current_status = job.status
            if current_status == JobStatus.RETRYING:
                assert_job_transition(current_status, JobStatus.QUEUED)
                job.status = JobStatus.QUEUED
                current_status = JobStatus.QUEUED

            assert_job_transition(current_status, JobStatus.PROCESSING)
            job.status = JobStatus.PROCESSING

            now = datetime.now(timezone.utc)
            job.attempt_count += 1
            job.claimed_at = now
            job.lease_expires_at = now + timedelta(seconds=LEASE_DURATION_SECONDS)

            recipient = job.recipient
            attempt_number = job.attempt_count

    return recipient, attempt_number


async def _record_outcome(
    *,
    job_id: uuid.UUID,
    channel: NotificationChannel,
    provider_name: str,
    success: bool,
    provider_message_id: str | None,
    error_message: str | None,
) -> None:
    event_id: uuid.UUID | None = None
    final_status: JobStatus | None = None
    retry_delay: float | None = None

    async with AsyncSessionLocal() as session:
        async with session.begin():
            try:
                job = (
                    (
                        await session.execute(
                            select(NotificationJob)
                            .where(NotificationJob.id == job_id)
                            .with_for_update()
                        )
                    )
                    .scalars()
                    .one()
                )
            except NoResultFound:
                logger.warning("job_outcome_skipped_missing", job_id=str(job_id))
                return

            if job.status != JobStatus.PROCESSING:
                # Shouldn't happen given the claim step, but if something
                # else (e.g. a concurrent recovery sweep) already moved
                # this job, don't clobber whatever state it's in now.
                logger.warning(
                    "job_outcome_skipped_unexpected_state",
                    job_id=str(job_id),
                    found_status=job.status.value,
                )
                return

            now = datetime.now(timezone.utc)
            session.add(
                NotificationDelivery(
                    job_id=job.id,
                    provider=provider_name,
                    provider_message_id=provider_message_id,
                    status=DeliveryStatus.DELIVERED if success else DeliveryStatus.FAILED,
                    delivered_at=now if success else None,
                    error_message=error_message,
                )
            )

            if success:
                assert_job_transition(JobStatus.PROCESSING, JobStatus.DELIVERED)
                job.status = JobStatus.DELIVERED
                job.processed_at = now
                job.last_error = None
                metrics.notifications_delivered_total.labels(
                    channel=channel.value, provider=provider_name
                ).inc()
                metrics.notification_delivery_duration_seconds.labels(
                    channel=channel.value
                ).observe((now - job.created_at).total_seconds())
            else:
                assert_job_transition(JobStatus.PROCESSING, JobStatus.FAILED)
                job.status = JobStatus.FAILED
                job.last_error = error_message
                metrics.notifications_failed_total.labels(
                    channel=channel.value, provider=provider_name
                ).inc()

                policy = get_retry_policy(channel.value)
                if policy.is_exhausted(job.attempt_count):
                    assert_job_transition(JobStatus.FAILED, JobStatus.DEAD_LETTERED)
                    job.status = JobStatus.DEAD_LETTERED
                    metrics.notifications_dead_lettered_total.labels(
                        channel=channel.value
                    ).inc()
                    session.add(
                        DeadLetterJob(
                            original_job_id=job.id,
                            reason=error_message or "Unknown provider failure",
                            payload={
                                "channel": channel.value,
                                "recipient": job.recipient,
                            },
                        )
                    )
                else:
                    assert_job_transition(JobStatus.FAILED, JobStatus.RETRYING)
                    job.status = JobStatus.RETRYING
                    metrics.notification_retries_total.labels(channel=channel.value).inc()
                    retry_delay = policy.delay_for_attempt(job.attempt_count)
                    job.scheduled_at = now + timedelta(seconds=retry_delay)

            job.claimed_at = None
            job.lease_expires_at = None
            final_status = job.status
            event_id = job.event_id

    if event_id is not None:
        await refresh_event_status(event_id)

    if final_status == JobStatus.RETRYING and retry_delay is not None:
        try:
            enqueue_notification_job(job_id, channel, countdown=retry_delay)
        except Exception:  # noqa: BLE001 -- broker hiccup must not crash the worker
            logger.error(
                "retry_enqueue_failed",
                job_id=str(job_id),
                channel=channel.value,
            )
