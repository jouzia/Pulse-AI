import uuid

import pytest
from sqlalchemy import select

from app.core.exceptions import JobAlreadyExistsError
from app.models.event import Event
from app.models.notification_job import NotificationJob
from app.schemas.event import EventCreateRequest
from app.services import event_service

pytestmark = pytest.mark.asyncio


async def test_job_creation_failure_rolls_back_the_event(db_session):
    """
    Forces the (event_id, channel) UNIQUE constraint to fire during job
    creation (via model_construct, which bypasses the Pydantic
    channels-must-be-unique validator) and asserts that afterward NEITHER
    the event NOR any job exists. Event and job creation commit together
    or not at all -- this is the guarantee, not just "duplicate events are
    rejected".
    """
    event_id = f"evt_rollback_{uuid.uuid4().hex[:8]}"
    payload = EventCreateRequest.model_construct(
        event_id=event_id,
        event_type="payment.succeeded",
        recipient="user@example.com",
        channels=["email", "email"],
        data={},
    )

    with pytest.raises(JobAlreadyExistsError):
        await event_service.create_event(db_session, payload)

    event_result = await db_session.execute(
        select(Event).where(Event.event_id == event_id)
    )
    assert event_result.scalar_one_or_none() is None

    jobs_result = await db_session.execute(select(NotificationJob))
    assert jobs_result.scalars().all() == []
