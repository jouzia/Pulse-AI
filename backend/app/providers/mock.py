"""
Deterministic local providers. These do not send real email/SMS/push —
see docs/architecture.md's "What's simulated" section. Failure behavior
is configurable per instance and never random, so tests built on these
never flake.
"""

import uuid

from app.providers.base import NotificationProvider, ProviderResult


class MockProvider(NotificationProvider):
    """
    failure_mode:
      "always_succeed"      -- every send() succeeds (default)
      "always_fail"         -- every send() fails
      "fail_n_then_succeed" -- the first `fail_count` calls on THIS
                               instance fail, then it succeeds. Tracked
                               via a per-instance counter, not global
                               state — construct a fresh instance per
                               test scenario.
    """

    def __init__(
        self,
        name: str,
        failure_mode: str = "always_succeed",
        fail_count: int = 0,
    ) -> None:
        self.name = name
        self.failure_mode = failure_mode
        self.fail_count = fail_count
        self._calls = 0

    def send(self, *, recipient: str, job_id: str) -> ProviderResult:
        self._calls += 1

        if self.failure_mode == "always_fail":
            return ProviderResult(
                success=False,
                error_message=f"{self.name}: simulated permanent failure",
            )

        if self.failure_mode == "fail_n_then_succeed" and self._calls <= self.fail_count:
            return ProviderResult(
                success=False,
                error_message=(
                    f"{self.name}: simulated failure (attempt {self._calls} of "
                    f"{self.fail_count})"
                ),
            )

        return ProviderResult(
            success=True,
            provider_message_id=f"mock-{self.name}-{uuid.uuid4().hex[:12]}",
        )


class MockEmailProvider(MockProvider):
    def __init__(self, **kwargs) -> None:
        super().__init__(name="mock-email", **kwargs)


class MockSMSProvider(MockProvider):
    def __init__(self, **kwargs) -> None:
        super().__init__(name="mock-sms", **kwargs)


class MockPushProvider(MockProvider):
    def __init__(self, **kwargs) -> None:
        super().__init__(name="mock-push", **kwargs)
