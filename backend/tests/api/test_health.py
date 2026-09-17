import pytest

pytestmark = pytest.mark.asyncio


async def test_health_returns_ok_without_auth(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


async def test_ready_reports_dependency_checks(client):
    resp = await client.get("/ready")
    assert resp.status_code in (200, 503)
    body = resp.json()
    assert set(body["checks"].keys()) == {"postgres", "redis"}


async def test_openapi_schema_loads(client):
    resp = await client.get("/openapi.json")
    assert resp.status_code == 200
    schema = resp.json()
    assert "/api/v1/events" in schema["paths"]


async def test_docs_page_loads(client):
    resp = await client.get("/docs")
    assert resp.status_code == 200
