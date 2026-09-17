"""
Event-level status aggregation rule (also documented in
docs/architecture.md):

  ALL jobs DELIVERED     -> event DELIVERED
  ANY job DEAD_LETTERED  -> event FAILED  (a channel permanently failed;
                                            the *jobs* that succeeded keep
                                            their own DELIVERED status --
                                            only the event's aggregate
                                            status reflects that the
                                            request as a whole did not
                                            fully succeed)
  ALL jobs still QUEUED  -> event QUEUED
  anything else (a mix of QUEUED/PROCESSING/FAILED/RETRYING/DELIVERED
  with no DEAD_LETTERED and not all DELIVERED)
                         -> event PROCESSING

Individual job rows are never rewritten by this function -- it only reads
job states and writes the event's own status column.

Note this deliberately does NOT go through assert_event_transition. That
table models the event's own one-way happy-path lifecycle
(RECEIVED -> ... -> DELIVERED); the aggregate computed here is a
many-to-one function of N job states that can legitimately move in either
direction as those jobs change (e.g. PROCESSING -> FAILED if a job that
was still in flight dead-letters, or even DELIVERED -> FAILED if a later
DLQ retry of one channel permanently fails after others already
delivered). Modeling that as a linear FSM would be the "unnecessary
abstraction" the brief warns against -- a plain recomputation is simpler
and exactly as correct.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.states import EventStatus, JobStatus
from app.db.session import AsyncSessionLocal
from app.models.event import Event
from app.models.notification_job import NotificationJob


async def refresh_event_status(event_id: uuid.UUID) -> None:
    async with AsyncSessionLocal() as session:
        async with session.begin():
            await _refresh_event_status(session, event_id)


async def _refresh_event_status(session: AsyncSession, event_id: uuid.UUID) -> None:
    jobs = (
        (
            await session.execute(
                select(NotificationJob).where(NotificationJob.event_id == event_id)
            )
        )
        .scalars()
        .all()
    )
    if not jobs:
        return

    event = (
        await session.execute(select(Event).where(Event.id == event_id))
    ).scalar_one_or_none()
    if event is None:
        return

    statuses = {job.status for job in jobs}

    if statuses <= {JobStatus.DELIVERED}:
        target = EventStatus.DELIVERED
    elif JobStatus.DEAD_LETTERED in statuses:
        target = EventStatus.FAILED
    elif statuses <= {JobStatus.QUEUED}:
        target = EventStatus.QUEUED
    else:
        target = EventStatus.PROCESSING

    if event.status == target:
        return

    event.status = target
    if target in (EventStatus.DELIVERED, EventStatus.FAILED):
        event.processed_at = datetime.now(timezone.utc)
