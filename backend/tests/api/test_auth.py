import pytest

pytestmark = pytest.mark.asyncio


async def test_missing_api_key_returns_401(client, make_event_payload):
    resp = await client.post("/api/v1/events", json=make_event_payload())
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "INVALID_CREDENTIALS"


async def test_invalid_api_key_returns_401(client, make_event_payload):
    resp = await client.post(
        "/api/v1/events",
        json=make_event_payload(),
        headers={"X-API-Key": "definitely-wrong"},
    )
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "INVALID_CREDENTIALS"


async def test_valid_api_key_is_accepted(client, api_key_headers, make_event_payload):
    resp = await client.post(
        "/api/v1/events", json=make_event_payload(), headers=api_key_headers
    )
    assert resp.status_code == 201


async def test_auth_failure_never_returns_500(client, make_event_payload):
    resp = await client.post(
        "/api/v1/events",
        json=make_event_payload(),
        headers={"X-API-Key": ""},
    )
    assert resp.status_code == 401
