import uuid

import pytest
from sqlalchemy import select

from app.core.states import JobStatus, NotificationChannel
from app.models.event import Event
from app.models.notification_delivery import NotificationDelivery
from app.models.notification_job import NotificationJob
from app.providers.mock import MockEmailProvider
from app.schemas.event import EventCreateRequest
from app.services import event_service
from app.workers import tasks as tasks_module

pytestmark = pytest.mark.asyncio


class _AlwaysDenyLimiter:
    async def allow(self, channel):
        return False


async def test_rate_limited_job_is_not_treated_as_a_provider_failure(
    db_session, set_provider, monkeypatch
):
    """
    Step 10's requirement, proven directly: when the rate limiter denies
    capacity, the job must be left exactly as it was -- no attempt
    consumed, no delivery record, no RetryPolicy involvement. Throttling
    is not a provider failure.
    """
    set_provider(NotificationChannel.EMAIL, MockEmailProvider(failure_mode="always_succeed"))

    payload = EventCreateRequest(
        event_id=f"evt_{uuid.uuid4().hex[:10]}",
        event_type="payment.succeeded",
        recipient="user@example.com",
        channels=["email"],
        data={},
    )
    response = await event_service.create_event(db_session, payload)
    event_row = (
        await db_session.execute(select(Event).where(Event.event_id == response.event_id))
    ).scalar_one()
    job = (
        await db_session.execute(
            select(NotificationJob).where(NotificationJob.event_id == event_row.id)
        )
    ).scalar_one()

    monkeypatch.setattr(tasks_module, "get_rate_limiter", lambda: _AlwaysDenyLimiter())

    await tasks_module._process_notification_job(job.id, job.channel)

    await db_session.refresh(job)
    assert job.status == JobStatus.QUEUED, "throttled job must stay exactly as it was"
    assert job.attempt_count == 0, "throttling must not consume an attempt"
    assert job.claimed_at is None

    deliveries = (
        (
            await db_session.execute(
                select(NotificationDelivery).where(NotificationDelivery.job_id == job.id)
            )
        )
        .scalars()
        .all()
    )
    assert deliveries == [], "throttling must not create a delivery record"
