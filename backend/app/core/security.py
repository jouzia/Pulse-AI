"""
Simple API-key authentication for Phase 2.

The key lives in environment configuration (PULSE_API_KEY / Settings.api_key)
— there is no persistent API-key table in this phase, so there is nothing
to hash or store. If a multi-key/persistent scheme is introduced later,
keys must be hashed at rest; never store them in plaintext.
"""

import hmac

from fastapi import Header

from app.core.config import get_settings
from app.core.exceptions import InvalidCredentialsError


async def require_api_key(
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> None:
    settings = get_settings()

    # Short-circuit on None before compare_digest (which requires two
    # str/bytes arguments) — and use compare_digest rather than `==` so a
    # missing or wrong key takes the same time either way, never revealing
    # a partial match through timing.
    if x_api_key is None or not hmac.compare_digest(x_api_key, settings.api_key):
        raise InvalidCredentialsError("Missing or invalid API key.")
