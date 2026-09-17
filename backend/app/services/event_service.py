"""
Event service: the only place event/job creation and retrieval logic
lives, so route handlers stay thin (auth -> validation -> this -> response
model) and the transactional/idempotency behavior isn't duplicated across
handlers.
"""

import uuid

import structlog
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import metrics
from app.core.exceptions import (
    EventAlreadyExistsError,
    EventNotFoundError,
    JobAlreadyExistsError,
    JobNotFoundError,
)
from app.core.states import EventStatus, JobStatus, assert_event_transition
from app.models.event import Event
from app.models.notification_delivery import NotificationDelivery
from app.models.notification_job import NotificationJob
from app.schemas.event import (
    EventCreateRequest,
    EventListItem,
    EventListResponse,
    EventResponse,
    JobSummary,
)
from app.schemas.ops import DeliveryAttempt, JobDetailResponse
from app.workers.dispatch import enqueue_notification_job

logger = structlog.get_logger(__name__)


async def create_event(db: AsyncSession, payload: EventCreateRequest) -> EventResponse:
    """
    Creates the event and one notification_job per requested channel in a
    single transaction: either both the event and all of its jobs commit,
    or none of them do.

    Duplicate event_id is NOT checked with a SELECT-then-INSERT — that
    check has a race window between the read and the write under
    concurrent requests. The events.event_id UNIQUE constraint is the
    actual source of truth; a violation surfaces here as an
    IntegrityError from the flush, which we translate into the domain
    EventAlreadyExistsError. Only one concurrent INSERT can ever win.
    """
    event = Event(
        event_id=payload.event_id,
        event_type=payload.event_type,
        payload=payload.data,
        status=EventStatus.RECEIVED,
    )

    # State transitions go through the Phase 1 transition table rather
    # than being written directly, so an illegal jump can't be introduced
    # here by a future edit without raising InvalidStateTransition.
    assert_event_transition(EventStatus.RECEIVED, EventStatus.VALIDATED)
    event.status = EventStatus.VALIDATED
    assert_event_transition(EventStatus.VALIDATED, EventStatus.QUEUED)
    event.status = EventStatus.QUEUED

    db.add(event)

    try:
        await db.flush()  # assigns event.id; surfaces event_id UNIQUE violation

        jobs = [
            NotificationJob(
                event_id=event.id,
                recipient=payload.recipient,
                channel=channel,
                status=JobStatus.QUEUED,
                max_attempts=5,
            )
            for channel in payload.channels
        ]
        db.add_all(jobs)
        await db.flush()  # surfaces (event_id, channel) UNIQUE violation

        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        constraint = getattr(getattr(exc, "orig", None), "constraint_name", None)
        if constraint == "uq_job_event_channel":
            raise JobAlreadyExistsError(
                "A notification job for this event and channel already exists."
            ) from exc
        raise EventAlreadyExistsError(
            f"An event with event_id '{payload.event_id}' already exists."
        ) from exc

    metrics.events_received_total.labels(event_type=payload.event_type).inc()

    await db.refresh(event)
    for job in jobs:
        await db.refresh(job)

    # Enqueue only after commit succeeds -- publishing before commit risks
    # a worker claiming a job that a rolled-back transaction never
    # actually persisted. This does leave a real (documented, not
    # papered-over) failure window: if the process crashes or Redis is
    # briefly unreachable between the commit above and these calls, a job
    # can sit QUEUED with no task ever published. app/workers/recovery.py
    # sweeps for exactly that case (QUEUED, unclaimed, older than a
    # threshold) and republishes it -- this is the concrete mechanism
    # behind the "at-least-once, not exactly-once" guarantee documented in
    # docs/architecture.md.
    for job in jobs:
        try:
            enqueue_notification_job(job.id, job.channel)
        except Exception:  # noqa: BLE001 -- broker hiccup must not fail a request whose event already committed
            logger.error(
                "event_job_enqueue_failed",
                event_id=str(event.id),
                job_id=str(job.id),
                channel=job.channel.value,
            )

    return EventResponse(
        event_id=event.event_id,
        event_type=event.event_type,
        status=event.status,
        created_at=event.created_at,
        jobs=[
            JobSummary(
                job_id=str(job.id),
                channel=job.channel,
                status=job.status,
                attempt_count=job.attempt_count,
            )
            for job in jobs
        ],
    )


async def get_event(db: AsyncSession, event_id: str) -> EventResponse:
    result = await db.execute(select(Event).where(Event.event_id == event_id))
    event = result.scalar_one_or_none()
    if event is None:
        raise EventNotFoundError(f"No event found with event_id '{event_id}'.")

    jobs_result = await db.execute(
        select(NotificationJob).where(NotificationJob.event_id == event.id)
    )
    jobs = jobs_result.scalars().all()

    return EventResponse(
        event_id=event.event_id,
        event_type=event.event_type,
        status=event.status,
        created_at=event.created_at,
        jobs=[
            JobSummary(
                job_id=str(job.id),
                channel=job.channel,
                status=job.status,
                attempt_count=job.attempt_count,
            )
            for job in jobs
        ],
    )


async def list_events(
    db: AsyncSession,
    page: int,
    page_size: int,
    status_filter: EventStatus | None,
    event_type_filter: str | None,
) -> EventListResponse:
    """Database-level pagination and filtering — never loads the full table."""
    query = select(Event)
    count_query = select(func.count()).select_from(Event)

    if status_filter is not None:
        query = query.where(Event.status == status_filter)
        count_query = count_query.where(Event.status == status_filter)
    if event_type_filter is not None:
        query = query.where(Event.event_type == event_type_filter)
        count_query = count_query.where(Event.event_type == event_type_filter)

    total = (await db.execute(count_query)).scalar_one()

    query = (
        query.order_by(Event.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    events = (await db.execute(query)).scalars().all()

    return EventListResponse(
        items=[
            EventListItem(
                event_id=event.event_id,
                event_type=event.event_type,
                status=event.status,
                created_at=event.created_at,
            )
            for event in events
        ],
        page=page,
        page_size=page_size,
        total=total,
    )


async def get_job(db: AsyncSession, job_id: str) -> JobDetailResponse:
    """
    Full job detail including its delivery-attempt history -- backs the
    dashboard's event detail view (app/api/v1/jobs.py). Deliberately
    richer than the JobSummary embedded in EventResponse, which only
    carries channel/status/attempt_count: an operator debugging a
    failure needs claimed_at/lease_expires_at and the actual per-attempt
    provider errors, not just the current status.
    """
    try:
        job_uuid = uuid.UUID(job_id)
    except ValueError as exc:
        raise JobNotFoundError(f"No job found with id '{job_id}'.") from exc

    job = (
        await db.execute(select(NotificationJob).where(NotificationJob.id == job_uuid))
    ).scalar_one_or_none()
    if job is None:
        raise JobNotFoundError(f"No job found with id '{job_id}'.")

    deliveries = (
        (
            await db.execute(
                select(NotificationDelivery)
                .where(NotificationDelivery.job_id == job.id)
                .order_by(NotificationDelivery.attempted_at)
            )
        )
        .scalars()
        .all()
    )

    return JobDetailResponse(
        job_id=str(job.id),
        event_id=str(job.event_id),
        channel=job.channel.value,
        status=job.status.value,
        attempt_count=job.attempt_count,
        max_attempts=job.max_attempts,
        recipient=job.recipient,
        scheduled_at=job.scheduled_at,
        claimed_at=job.claimed_at,
        lease_expires_at=job.lease_expires_at,
        created_at=job.created_at,
        updated_at=job.updated_at,
        last_error=job.last_error,
        deliveries=[DeliveryAttempt.model_validate(d) for d in deliveries],
    )
