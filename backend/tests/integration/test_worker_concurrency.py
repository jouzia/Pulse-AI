import asyncio
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
from app.workers.tasks import _process_notification_job

pytestmark = pytest.mark.asyncio


async def test_duplicate_task_execution_produces_exactly_one_delivery(
    db_session, set_provider
):
    """
    Simulates Celery redelivering the same task message: two concurrent
    calls to _process_notification_job for the SAME job_id, fired via
    asyncio.gather (no sleeps). Exactly one must actually process the
    job -- the guarantee comes from FOR UPDATE SKIP LOCKED plus the
    status filter in _claim_job, not from any lock this test constructs.
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

    await asyncio.gather(
        _process_notification_job(job.id, job.channel),
        _process_notification_job(job.id, job.channel),
    )

    deliveries = (
        (
            await db_session.execute(
                select(NotificationDelivery).where(NotificationDelivery.job_id == job.id)
            )
        )
        .scalars()
        .all()
    )
    assert len(deliveries) == 1

    await db_session.refresh(job)
    assert job.status == JobStatus.DELIVERED
    assert job.attempt_count == 1
