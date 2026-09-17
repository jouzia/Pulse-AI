import pytest

from app.services import event_service

pytestmark = pytest.mark.asyncio


async def test_unhandled_exception_returns_generic_500_without_leaking_details(
    client, api_key_headers, make_event_payload, monkeypatch
):
    """
    Forces a genuine unhandled exception (not a PulseError) inside the
    request path and confirms the client sees only the generic envelope
    -- never the exception message, type, or a traceback. The real
    detail is expected to go to structured logs instead (see
    app/main.py's unhandled_exception_handler); this test can't observe
    stdout, but it can prove the response body stays generic regardless
    of what the underlying exception says.
    """

    async def _boom(*args, **kwargs):
        raise RuntimeError("some internal detail that must never reach the client")

    monkeypatch.setattr(event_service, "create_event", _boom)

    resp = await client.post(
        "/api/v1/events", json=make_event_payload(), headers=api_key_headers
    )

    assert resp.status_code == 500
    body = resp.json()
    assert body == {
        "error": {
            "code": "INTERNAL_ERROR",
            "message": "An unexpected error occurred.",
        }
    }
    assert "some internal detail" not in resp.text
    assert "RuntimeError" not in resp.text
    assert "Traceback" not in resp.text
