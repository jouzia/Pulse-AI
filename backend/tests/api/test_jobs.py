import pytest
from sqlalchemy import select

from app.models.event import Event
from app.models.notification_job import NotificationJob

pytestmark = pytest.mark.asyncio


async def test_job_detail_requires_auth(client):
    resp = await client.get("/api/v1/jobs/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 401


async def test_job_detail_not_found(client, api_key_headers):
    resp = await client.get(
        "/api/v1/jobs/00000000-0000-0000-0000-000000000000", headers=api_key_headers
    )
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "JOB_NOT_FOUND"


async def test_job_detail_malformed_id_returns_404_not_500(client, api_key_headers):
    resp = await client.get("/api/v1/jobs/not-a-uuid", headers=api_key_headers)
    assert resp.status_code == 404


async def test_job_detail_for_real_job(
    client, api_key_headers, make_event_payload, db_session
):
    create_resp = await client.post(
        "/api/v1/events", json=make_event_payload(channels=["email"]), headers=api_key_headers
    )
    event_id = create_resp.json()["event_id"]

    event_row = (
        await db_session.execute(select(Event).where(Event.event_id == event_id))
    ).scalar_one()
    job = (
        await db_session.execute(
            select(NotificationJob).where(NotificationJob.event_id == event_row.id)
        )
    ).scalar_one()

    resp = await client.get(f"/api/v1/jobs/{job.id}", headers=api_key_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["job_id"] == str(job.id)
    assert body["event_id"] == str(event_row.id)
    assert body["channel"] == "email"
    assert body["status"] == "queued"
    assert body["deliveries"] == []
