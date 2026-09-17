"""
The only place a channel gets mapped to a provider instance. Workers call
get_provider(channel); no if/elif chains on channel anywhere else.

Swapping a mock for a real provider later (e.g. real email via SES) means
changing exactly one line here, not touching worker logic.
"""

from app.core.states import NotificationChannel
from app.providers.base import NotificationProvider
from app.providers.mock import MockEmailProvider, MockPushProvider, MockSMSProvider

_PROVIDERS: dict[NotificationChannel, NotificationProvider] = {
    NotificationChannel.EMAIL: MockEmailProvider(),
    NotificationChannel.SMS: MockSMSProvider(),
    NotificationChannel.PUSH: MockPushProvider(),
}


def get_provider(channel: NotificationChannel) -> NotificationProvider:
    return _PROVIDERS[channel]
