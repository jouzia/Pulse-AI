from app.core.states import NotificationChannel
from app.providers.registry import get_provider
from app.workers.dispatch import queue_for_channel


def test_get_provider_maps_each_channel_correctly():
    assert get_provider(NotificationChannel.EMAIL).name == "mock-email"
    assert get_provider(NotificationChannel.SMS).name == "mock-sms"
    assert get_provider(NotificationChannel.PUSH).name == "mock-push"


def test_queue_naming_matches_channel():
    assert queue_for_channel(NotificationChannel.EMAIL) == "notifications.email"
    assert queue_for_channel(NotificationChannel.SMS) == "notifications.sms"
    assert queue_for_channel(NotificationChannel.PUSH) == "notifications.push"
