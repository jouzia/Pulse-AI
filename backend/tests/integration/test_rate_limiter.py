"""
Rate limiter tests. These require a real, reachable Redis (set REDIS_URL,
same pattern as DATABASE_URL for the Postgres-backed tests elsewhere in
this suite) -- the whole point of this limiter is atomicity across
concurrent callers via a Redis Lua script, which cannot be meaningfully
tested against a mock.
"""

import asyncio
import time

import pytest

from app.core.rate_limiter import RateLimiter
from app.core.states import NotificationChannel

pytestmark = pytest.mark.asyncio

REDIS_URL = "redis://localhost:6379/0"


def _limiter(**limits_per_minute: int) -> RateLimiter:
    return RateLimiter(
        redis_url=REDIS_URL,
        limits_per_minute={
            NotificationChannel[name.upper()]: limit
            for name, limit in limits_per_minute.items()
        },
    )


@pytest.fixture(autouse=True)
async def _clean_buckets():
    limiter = _limiter(email=1, sms=1, push=1)
    client = limiter._get_client()
    await client.delete("rate_limit:email", "rate_limit:sms", "rate_limit:push")
    yield
    await client.delete("rate_limit:email", "rate_limit:sms", "rate_limit:push")
    await limiter.aclose()


async def test_allows_requests_within_capacity():
    limiter = _limiter(email=5)
    try:
        results = [await limiter.allow(NotificationChannel.EMAIL) for _ in range(5)]
        assert all(results)
    finally:
        await limiter.aclose()


async def test_denies_once_capacity_is_exhausted():
    limiter = _limiter(email=2)
    try:
        assert await limiter.allow(NotificationChannel.EMAIL) is True
        assert await limiter.allow(NotificationChannel.EMAIL) is True
        assert await limiter.allow(NotificationChannel.EMAIL) is False
    finally:
        await limiter.aclose()


async def test_refills_over_time():
    # capacity=60/min -> refill_rate = 1 token/sec, so waiting just over
    # a second after exhausting the bucket should yield exactly one more
    # token -- deterministic without needing to wait a full minute.
    limiter = _limiter(email=60)
    client = limiter._get_client()
    try:
        await client.hset(
            "rate_limit:email", mapping={"tokens": 0, "last_refill": time.time()}
        )
        assert await limiter.allow(NotificationChannel.EMAIL) is False
        await asyncio.sleep(1.1)
        assert await limiter.allow(NotificationChannel.EMAIL) is True
    finally:
        await limiter.aclose()


async def test_per_channel_limits_are_independent():
    limiter = _limiter(email=1, sms=1)
    try:
        assert await limiter.allow(NotificationChannel.EMAIL) is True
        assert await limiter.allow(NotificationChannel.EMAIL) is False
        # SMS's bucket is untouched by EMAIL's exhaustion.
        assert await limiter.allow(NotificationChannel.SMS) is True
    finally:
        await limiter.aclose()


async def test_unconfigured_channel_is_treated_as_unlimited():
    limiter = RateLimiter(redis_url=REDIS_URL, limits_per_minute={})
    try:
        results = [await limiter.allow(NotificationChannel.PUSH) for _ in range(20)]
        assert all(results)
    finally:
        await limiter.aclose()


async def test_redis_unavailable_fails_open():
    # Port 1 is a reserved/typically-closed port -- nothing should be
    # listening, simulating Redis being unreachable.
    limiter = RateLimiter(
        redis_url="redis://localhost:1/0",
        limits_per_minute={NotificationChannel.EMAIL: 1},
    )
    try:
        allowed = await limiter.allow(NotificationChannel.EMAIL)
        assert allowed is True, "must fail open, not closed, when Redis is unreachable"
    finally:
        await limiter.aclose()


async def test_concurrent_callers_never_exceed_capacity():
    """
    The atomicity claim this whole module rests on: fire more concurrent
    callers than the bucket has capacity for, via asyncio.gather (real
    concurrency, no sleeps), and confirm exactly `capacity` succeed --
    proving the Lua script serializes the read-refill-write cycle rather
    than letting concurrent callers race past each other.
    """
    limiter = _limiter(email=5)
    try:
        results = await asyncio.gather(
            *[limiter.allow(NotificationChannel.EMAIL) for _ in range(20)]
        )
        assert sum(results) == 5
    finally:
        await limiter.aclose()
