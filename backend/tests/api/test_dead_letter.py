import uuid

import pytest
from sqlalchemy import select

from app.core.states import JobStatus, NotificationChannel
from app.models.dead_letter_job import DeadLetterJob
from app.models.event import Event
from app.models.notification_job import NotificationJob
from app.providers.mock import MockEmailProvider
from app.schemas.event import EventCreateRequest
from app.services import event_service
from app.workers.tasks import _process_notification_job

pytestmark = pytest.mark.asyncio


async def _create_dead_lettered_job(db_session, set_provider):
    set_provider(NotificationChannel.EMAIL, MockEmailProvider(failure_mode="always_fail"))
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
    job.max_attempts = 1
    await db_session.commit()

    await _process_notification_job(job.id, job.channel)
    await db_session.refresh(job)
    assert job.status == JobStatus.DEAD_LETTERED

    dl_row = (
        await db_session.execute(
            select(DeadLetterJob).where(DeadLetterJob.original_job_id == job.id)
        )
    ).scalar_one()
    return job, dl_row


async def test_list_requires_auth(client):
    resp = await client.get("/api/v1/dead-letter")
    assert resp.status_code == 401


async def test_list_empty(client, api_key_headers):
    resp = await client.get("/api/v1/dead-letter", headers=api_key_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["items"] == []
    assert body["total"] == 0


async def test_list_shows_dead_lettered_job(client, api_key_headers, db_session, set_provider):
    job, dl_row = await _create_dead_lettered_job(db_session, set_provider)

    resp = await client.get("/api/v1/dead-letter", headers=api_key_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["id"] == str(dl_row.id)
    assert body["items"][0]["channel"] == "email"
    assert body["items"][0]["resolved_at"] is None
    # Regression: event_id must be the human-readable business key (as
    # accepted by GET /api/v1/events/{event_id}), not the internal event
    # UUID -- NotificationJob.event_id is a FK holding that UUID, and an
    # earlier version of this endpoint exposed it directly under the
    # "event_id" field name, which would have made every dashboard
    # "view event" link 404.
    event_row = (
        await db_session.execute(select(Event).where(Event.id == job.event_id))
    ).scalar_one()
    assert body["items"][0]["event_id"] == event_row.event_id
    assert body["items"][0]["event_id"] != str(job.event_id)


async def test_list_pagination(client, api_key_headers, db_session, set_provider):
    await _create_dead_lettered_job(db_session, set_provider)
    await _create_dead_lettered_job(db_session, set_provider)

    resp = await client.get(
        "/api/v1/dead-letter", params={"page": 1, "page_size": 1}, headers=api_key_headers
    )
    body = resp.json()
    assert len(body["items"]) == 1
    assert body["total"] == 2


async def test_retry_not_found(client, api_key_headers):
    resp = await client.post(
        "/api/v1/dead-letter/00000000-0000-0000-0000-000000000000/retry",
        headers=api_key_headers,
    )
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "DEAD_LETTER_JOB_NOT_FOUND"


async def test_retry_requeues_the_job(client, api_key_headers, db_session, set_provider):
    job, dl_row = await _create_dead_lettered_job(db_session, set_provider)

    resp = await client.post(
        f"/api/v1/dead-letter/{dl_row.id}/retry", headers=api_key_headers
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "queued"

    await db_session.refresh(job)
    assert job.status == JobStatus.QUEUED
    assert job.attempt_count == 0


async def test_retry_twice_returns_conflict(client, api_key_headers, db_session, set_provider):
    _, dl_row = await _create_dead_lettered_job(db_session, set_provider)

    first = await client.post(
        f"/api/v1/dead-letter/{dl_row.id}/retry", headers=api_key_headers
    )
    assert first.status_code == 200

    second = await client.post(
        f"/api/v1/dead-letter/{dl_row.id}/retry", headers=api_key_headers
    )
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "DEAD_LETTER_JOB_ALREADY_RESOLVED"
