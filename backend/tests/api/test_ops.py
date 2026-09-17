import pytest

pytestmark = pytest.mark.asyncio


async def test_overview_requires_auth(client):
    resp = await client.get("/api/v1/ops/overview")
    assert resp.status_code == 401


async def test_overview_shape_with_no_data(client, api_key_headers):
    resp = await client.get("/api/v1/ops/overview", headers=api_key_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert set(body["events_by_status"].keys()) >= {"received", "queued", "delivered"}
    assert set(body["jobs_by_channel_and_status"].keys()) == {"email", "sms", "push"}
    assert body["dead_letter_count"] == 0
    assert "configured_rate_limits_per_minute" in body
    assert set(body["configured_rate_limits_per_minute"].keys()) == {"email", "sms", "push"}


async def test_overview_reflects_a_created_event(client, api_key_headers, make_event_payload):
    await client.post(
        "/api/v1/events", json=make_event_payload(channels=["email"]), headers=api_key_headers
    )
    resp = await client.get("/api/v1/ops/overview", headers=api_key_headers)
    body = resp.json()
    assert body["jobs_by_channel_and_status"]["email"]["queued"] >= 1
