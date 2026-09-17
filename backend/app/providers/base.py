"""
Minimal notification provider abstraction. Exists because Pulse genuinely
supports multiple channels with different send mechanics — not as a
speculative interface for its own sake. A worker needs exactly one
operation from a provider: send it, get back enough to persist a
delivery record.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class ProviderResult:
    success: bool
    provider_message_id: str | None = None
    error_message: str | None = None


class NotificationProvider:
    name: str = "base"

    def send(self, *, recipient: str, job_id: str) -> ProviderResult:
        raise NotImplementedError
