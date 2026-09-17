import asyncio
import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.main import app
from app.models.event import Event
from app.models.notification_job import NotificationJob

pytestmark = pytest.mark.asyncio


async def test_concurrent_duplicate_event_submission_is_safe(api_key_headers, db_session):
    """
    Fires 10 genuinely concurrent POST /events requests with the same
    event_id via asyncio.gather (no sleeps, no manufactured ordering) and
    asserts exactly one succeeds. The correctness guarantee comes from the
    events.event_id UNIQUE constraint in Postgres -- if this test is
    flaky, that constraint (or the transaction boundary around it) is
    broken, not the test.
    """
    event_id = f"evt_concurrent_{uuid.uuid4().hex[:8]}"
    payload = {
        "event_id": event_id,
        "event_type": "payment.succeeded",
        "recipient": "user@example.com",
        "channels": ["email", "sms", "push"],
        "data": {"amount": 999},
    }

    concurrency = 10
    transport = ASGITransport(app=app)

    async def _submit():
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            return await ac.post("/api/v1/events", json=payload, headers=api_key_headers)

    responses = await asyncio.gather(*[_submit() for _ in range(concurrency)])
    statuses = sorted(r.status_code for r in responses)

    assert statuses.count(201) == 1
    assert statuses.count(409) == concurrency - 1

    events_result = await db_session.execute(
        select(Event).where(Event.event_id == event_id)
    )
    matching_events = events_result.scalars().all()
    assert len(matching_events) == 1

    jobs_result = await db_session.execute(
        select(NotificationJob).where(NotificationJob.event_id == matching_events[0].id)
    )
    jobs = jobs_result.scalars().all()
    assert {job.channel.value for job in jobs} == {"email", "sms", "push"}
