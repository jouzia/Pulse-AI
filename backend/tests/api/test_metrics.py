import pytest

pytestmark = pytest.mark.asyncio


async def test_metrics_endpoint_returns_prometheus_format(client):
    resp = await client.get("/metrics")
    assert resp.status_code == 200
    assert "text/plain" in resp.headers["content-type"]
    assert "pulse_queue_depth" in resp.text


async def test_metrics_reflects_a_created_event(client, api_key_headers, make_event_payload):
    await client.post("/api/v1/events", json=make_event_payload(), headers=api_key_headers)
    resp = await client.get("/metrics")
    assert "pulse_events_received_total" in resp.text
