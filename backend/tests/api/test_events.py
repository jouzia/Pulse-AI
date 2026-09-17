import pytest

pytestmark = pytest.mark.asyncio


# --- Creation --------------------------------------------------------------


async def test_create_event_valid_multi_channel(client, api_key_headers, make_event_payload):
    resp = await client.post(
        "/api/v1/events", json=make_event_payload(), headers=api_key_headers
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "queued"
    assert {j["channel"] for j in body["jobs"]} == {"email", "push"}
    assert all(j["attempt_count"] == 0 for j in body["jobs"])
    assert all(j["job_id"] for j in body["jobs"]), "job_id must be present for dashboard deep-links"
    assert all(j["status"] == "queued" for j in body["jobs"])


async def test_create_event_single_channel(client, api_key_headers, make_event_payload):
    resp = await client.post(
        "/api/v1/events",
        json=make_event_payload(channels=["sms"]),
        headers=api_key_headers,
    )
    assert resp.status_code == 201
    assert len(resp.json()["jobs"]) == 1
    assert resp.json()["jobs"][0]["channel"] == "sms"


async def test_create_event_missing_required_field_returns_422(
    client, api_key_headers, make_event_payload
):
    payload = make_event_payload()
    del payload["event_type"]
    resp = await client.post("/api/v1/events", json=payload, headers=api_key_headers)
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


async def test_create_event_invalid_channel_returns_422(
    client, api_key_headers, make_event_payload
):
    resp = await client.post(
        "/api/v1/events",
        json=make_event_payload(channels=["carrier-pigeon"]),
        headers=api_key_headers,
    )
    assert resp.status_code == 422


async def test_create_event_duplicate_channels_in_request_returns_422(
    client, api_key_headers, make_event_payload
):
    resp = await client.post(
        "/api/v1/events",
        json=make_event_payload(channels=["email", "email"]),
        headers=api_key_headers,
    )
    assert resp.status_code == 422


# --- Duplicate event_id (idempotency) ---------------------------------------


async def test_duplicate_event_id_returns_409(client, api_key_headers, make_event_payload):
    payload = make_event_payload()
    first = await client.post("/api/v1/events", json=payload, headers=api_key_headers)
    assert first.status_code == 201

    second = await client.post("/api/v1/events", json=payload, headers=api_key_headers)
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "EVENT_ALREADY_EXISTS"


# --- Retrieval ---------------------------------------------------------------


async def test_get_event_existing(client, api_key_headers, make_event_payload):
    payload = make_event_payload()
    await client.post("/api/v1/events", json=payload, headers=api_key_headers)

    resp = await client.get(
        f"/api/v1/events/{payload['event_id']}", headers=api_key_headers
    )
    assert resp.status_code == 200
    assert resp.json()["event_id"] == payload["event_id"]


async def test_get_event_nonexistent_returns_404(client, api_key_headers):
    resp = await client.get("/api/v1/events/evt_does_not_exist", headers=api_key_headers)
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "EVENT_NOT_FOUND"


# --- Pagination & filtering ---------------------------------------------------


async def test_list_events_page_size(client, api_key_headers, make_event_payload):
    for _ in range(5):
        await client.post(
            "/api/v1/events", json=make_event_payload(), headers=api_key_headers
        )

    resp = await client.get(
        "/api/v1/events", params={"page": 1, "page_size": 2}, headers=api_key_headers
    )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["items"]) == 2
    assert body["total"] >= 5
    assert body["page"] == 1
    assert body["page_size"] == 2


async def test_list_events_page_number_advances(
    client, api_key_headers, make_event_payload
):
    for _ in range(3):
        await client.post(
            "/api/v1/events", json=make_event_payload(), headers=api_key_headers
        )

    page1 = await client.get(
        "/api/v1/events", params={"page": 1, "page_size": 1}, headers=api_key_headers
    )
    page2 = await client.get(
        "/api/v1/events", params={"page": 2, "page_size": 1}, headers=api_key_headers
    )
    assert page1.json()["items"][0]["event_id"] != page2.json()["items"][0]["event_id"]


async def test_list_events_filter_by_event_type(
    client, api_key_headers, make_event_payload
):
    await client.post(
        "/api/v1/events",
        json=make_event_payload(event_type="payment.succeeded"),
        headers=api_key_headers,
    )
    await client.post(
        "/api/v1/events",
        json=make_event_payload(event_type="user.signup"),
        headers=api_key_headers,
    )

    resp = await client.get(
        "/api/v1/events",
        params={"event_type": "user.signup"},
        headers=api_key_headers,
    )
    body = resp.json()
    assert len(body["items"]) >= 1
    assert all(item["event_type"] == "user.signup" for item in body["items"])


async def test_list_events_filter_by_status(client, api_key_headers, make_event_payload):
    await client.post(
        "/api/v1/events", json=make_event_payload(), headers=api_key_headers
    )

    resp = await client.get(
        "/api/v1/events", params={"status": "queued"}, headers=api_key_headers
    )
    assert resp.status_code == 200
    assert all(item["status"] == "queued" for item in resp.json()["items"])
