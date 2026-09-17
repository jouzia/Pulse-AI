"""
Redis-backed token bucket rate limiter, one bucket per channel.

Algorithm choice: token bucket over a fixed-window counter. A fixed
window (e.g. "INCR a counter, reset every 60s") is simpler but allows up
to 2x the configured limit in a burst that straddles two adjacent
windows -- a request at 0:59 and another at 1:01 both succeed even
though they're 2 seconds apart. A continuously-refilling token bucket
has no such boundary and maps directly onto "N per minute"
(capacity=N, refill_rate=N/60 tokens/second), which is exactly the unit
the existing settings (`rate_limit_email_per_minute` etc., defined back
in Phase 1) already use.

Atomicity: the read-refill-compare-write cycle runs as a single Redis
Lua script (EVAL). Redis executes a script to completion without
interleaving any other command, so this is safe across multiple
concurrent workers and API processes calling it at once -- a naive
"GET, compute in Python, SET" would race between the GET and the SET
under exactly the concurrent load this limiter exists to handle.

Redis failure policy: FAIL OPEN. If Redis is unreachable, `allow()`
returns True (do not throttle) rather than blocking all notification
delivery on the rate limiter's own availability. This is a deliberate
choice, not an oversight: a Redis outage should not silently halt every
outbound notification in the system. A payment-authorization gate would
likely choose the opposite (fail closed) -- the right choice depends on
which failure mode is worse for the system in question, and here an
unbounded-but-brief burst is judged less harmful than a total outage of
notification delivery.
"""

import time

import redis.asyncio as redis_asyncio
import structlog

from app.core.config import get_settings
from app.core.states import NotificationChannel

logger = structlog.get_logger(__name__)

# KEYS[1] = bucket key
# ARGV[1] = capacity (max tokens)
# ARGV[2] = refill_rate (tokens per second)
# ARGV[3] = now (unix timestamp, seconds, float)
# ARGV[4] = tokens requested (always 1 here -- one job attempt)
_TOKEN_BUCKET_SCRIPT = """
local bucket = redis.call('HMGET', KEYS[1], 'tokens', 'last_refill')
local tokens = tonumber(bucket[1])
local last_refill = tonumber(bucket[2])
local capacity = tonumber(ARGV[1])
local refill_rate = tonumber(ARGV[2])
local now = tonumber(ARGV[3])
local requested = tonumber(ARGV[4])

if tokens == nil then
    tokens = capacity
    last_refill = now
end

local elapsed = math.max(0, now - last_refill)
tokens = math.min(capacity, tokens + elapsed * refill_rate)

local allowed = 0
if tokens >= requested then
    tokens = tokens - requested
    allowed = 1
end

redis.call('HMSET', KEYS[1], 'tokens', tokens, 'last_refill', now)
redis.call('EXPIRE', KEYS[1], 3600)

return allowed
"""


class RateLimiter:
    """
    One token bucket per channel, keyed `rate_limit:{channel}` in Redis.
    `allow(channel)` consumes one token -- one notification job's
    provider-send attempt -- if capacity is available.

    A channel with a configured limit of 0 or less is treated as
    unlimited (returns True unconditionally) rather than as "always
    deny", since 0 is a much more likely misconfiguration ("rate limit
    not set") than an intentional full block, and failing open on
    misconfiguration matches the same fail-open philosophy as the Redis
    failure case.
    """

    def __init__(
        self, redis_url: str, limits_per_minute: dict[NotificationChannel, int]
    ) -> None:
        self._redis_url = redis_url
        self._limits = limits_per_minute
        self._client: redis_asyncio.Redis | None = None
        self._script = None

    def _get_client(self) -> redis_asyncio.Redis:
        # Created lazily, on first use within whichever event loop is
        # actually running -- never at construction time. See
        # app/workers/tasks.py's _run_and_dispose for why a Redis/DB
        # client must not be created once and reused across the
        # different event loops that asyncio.run() creates per Celery
        # task.
        if self._client is None:
            self._client = redis_asyncio.Redis.from_url(self._redis_url)
            self._script = self._client.register_script(_TOKEN_BUCKET_SCRIPT)
        return self._client

    async def allow(self, channel: NotificationChannel) -> bool:
        capacity = self._limits.get(channel)
        if not capacity or capacity <= 0:
            return True

        client = self._get_client()
        refill_rate = capacity / 60.0
        key = f"rate_limit:{channel.value}"
        now = time.time()

        try:
            result = await self._script(keys=[key], args=[capacity, refill_rate, now, 1])
        except Exception:  # noqa: BLE001 -- Redis boundary; fail open per module docstring
            logger.error("rate_limiter_redis_unavailable", channel=channel.value)
            return True

        return bool(int(result))

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None
            self._script = None


_rate_limiter: RateLimiter | None = None


def get_rate_limiter() -> RateLimiter:
    """
    Process-wide singleton for the *configuration* (limits, URL) -- but
    see _get_client above: the actual Redis connection inside it is
    created lazily per event loop, not shared across them.
    """
    global _rate_limiter
    if _rate_limiter is None:
        settings = get_settings()
        _rate_limiter = RateLimiter(
            redis_url=settings.redis_url,
            limits_per_minute={
                NotificationChannel.EMAIL: settings.rate_limit_email_per_minute,
                NotificationChannel.SMS: settings.rate_limit_sms_per_minute,
                NotificationChannel.PUSH: settings.rate_limit_push_per_minute,
            },
        )
    return _rate_limiter
