"""
Retry policy: exponential backoff with jitter, defined once and looked up
by channel rather than hardcoded at each call site.
"""

from dataclasses import dataclass
import random


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 5
    base_delay_seconds: float = 5.0
    multiplier: float = 6.0
    max_delay_seconds: float = 600.0
    jitter_ratio: float = 0.2

    def delay_for_attempt(self, attempt: int) -> float:
        """
        attempt is 1-indexed (the attempt that just failed).
        attempt=1 -> ~0s (immediate first retry)
        attempt=2 -> ~5s
        attempt=3 -> ~30s
        attempt=4 -> ~2m (capped/approximated by multiplier growth)
        attempt=5 -> ~10m (capped at max_delay_seconds)
        """
        if attempt <= 1:
            base = 0.0
        else:
            base = self.base_delay_seconds * (self.multiplier ** (attempt - 2))
        base = min(base, self.max_delay_seconds)

        if base == 0.0:
            return 0.0

        jitter_span = base * self.jitter_ratio
        return base + random.uniform(-jitter_span, jitter_span)

    def is_exhausted(self, attempt_count: int) -> bool:
        return attempt_count >= self.max_attempts


# Per-channel policies. Looked up by NotificationChannel, not duplicated
# inline in worker code. Channels can diverge (e.g. SMS providers often
# have tighter throughput) without touching worker logic.
DEFAULT_RETRY_POLICY = RetryPolicy()

RETRY_POLICIES: dict[str, RetryPolicy] = {
    "email": DEFAULT_RETRY_POLICY,
    "sms": RetryPolicy(max_attempts=5, base_delay_seconds=5.0, multiplier=6.0),
    "push": RetryPolicy(max_attempts=4, base_delay_seconds=3.0, multiplier=5.0),
}


def get_retry_policy(channel: str) -> RetryPolicy:
    return RETRY_POLICIES.get(channel, DEFAULT_RETRY_POLICY)
