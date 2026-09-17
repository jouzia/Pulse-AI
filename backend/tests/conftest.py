"""
Shared test fixtures.

These tests run against a real Postgres database — set DATABASE_URL to a
dedicated test database (never point this at a database you care about;
the schema is dropped and recreated per test session, and tables are
truncated between tests). Recommended:

    export DATABASE_URL=postgresql+asyncpg://pulse:pulse@localhost:5432/pulse_test
    export API_KEY=test-api-key
    pytest

Tests import app.main.app directly and drive it in-process via httpx's
ASGITransport rather than hitting a running uvicorn process — this is
what lets the concurrency test fire real concurrent requests without a
separate server process, while still exercising a real Postgres
connection pool per request.
"""

import os
import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://pulse:pulse@localhost:5432/pulse_test"
)
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("API_KEY", "test-api-key")

from app.core.config import get_settings  # noqa: E402
from app.core.rate_limiter import get_rate_limiter  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.db.session import AsyncSessionLocal, engine, get_db  # noqa: E402
from app.main import app  # noqa: E402
import app.models  # noqa: E402,F401 -- registers all tables on Base.metadata

get_settings.cache_clear()
settings = get_settings()

# Tests use the app's actual `engine`/`AsyncSessionLocal` (app/db/session.py)
# directly rather than standing up a second, parallel engine pointed at the
# same database -- worker functions called directly in tests (e.g.
# `_process_notification_job`) already use this exact engine internally, so
# using it here too means tests exercise the real object, including the
# cross-event-loop disposal fix described below.


@pytest_asyncio.fixture(scope="session", autouse=True)
async def _schema():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture(autouse=True)
async def _clean_tables():
    """
    Truncate all tables after each test so ordering never matters, and
    dispose the engine's connection pool afterward.

    The disposal matters beyond cleanliness: pytest-asyncio gives each
    test function its own event loop by default, but `engine` is a
    single module-level object reused across every test (and, within a
    test, by any worker function called directly). A connection checked
    into its pool during test A's loop is invalid once that loop closes
    -- test B (a different loop) reusing it would fail with a
    cross-event-loop error from asyncpg. Disposing after every test
    forces the next test's first query to open a fresh connection
    correctly scoped to its own loop. This is the exact same fix applied
    to the Celery worker in app/workers/tasks.py and
    app/workers/recovery.py, for the same underlying reason.
    """
    yield
    async with engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            await conn.execute(table.delete())
    await engine.dispose()
    await get_rate_limiter().aclose()


@pytest_asyncio.fixture(autouse=True)
def _override_db_dependency():
    async def _get_test_db():
        async with AsyncSessionLocal() as session:
            yield session

    app.dependency_overrides[get_db] = _get_test_db
    yield
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def db_session():
    """A direct session for tests that exercise the service layer, not HTTP."""
    async with AsyncSessionLocal() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def api_key_headers() -> dict[str, str]:
    return {"X-API-Key": settings.api_key}


@pytest.fixture
def set_provider():
    """
    Swap the provider registry's entry for a channel with a caller-built
    mock (a specific failure_mode/fail_count), so worker tests get
    deterministic, controlled behavior. Restores the original registry
    afterward so tests never leak provider state into each other.
    """
    from app.providers import registry

    originals = dict(registry._PROVIDERS)

    def _set(channel, provider) -> None:
        registry._PROVIDERS[channel] = provider

    yield _set

    registry._PROVIDERS.clear()
    registry._PROVIDERS.update(originals)


@pytest.fixture
def make_event_payload():
    def _make(**overrides) -> dict:
        payload = {
            "event_id": f"evt_{uuid.uuid4().hex[:12]}",
            "event_type": "payment.succeeded",
            "recipient": "user@example.com",
            "channels": ["email", "push"],
            "data": {"amount": 1499, "currency": "INR"},
        }
        payload.update(overrides)
        return payload

    return _make
