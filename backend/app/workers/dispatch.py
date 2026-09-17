"""
Enqueueing helpers. Kept separate from app/workers/tasks.py so that
app/services/event_service.py (running in the API process) only needs a
thin function call to publish a job — not the worker's full processing
logic and its provider/DB dependencies at import time.

process_notification_job is imported lazily, inside the function, to
avoid a module-level circular import with celery_app.py (tasks.py imports
celery_app; celery_app.py imports tasks.py to register it).
"""

import uuid

from app.core.states import NotificationChannel


def queue_for_channel(channel: NotificationChannel) -> str:
    """
    notifications.email / notifications.sms / notifications.push — one
    queue per channel, so a burst on one channel can't starve the others,
    and workers can be scaled per-channel later if needed.
    """
    return f"notifications.{channel.value}"


def enqueue_notification_job(
    job_id: uuid.UUID,
    channel: NotificationChannel,
    countdown: float | None = None,
) -> None:
    from app.workers.tasks import process_notification_job

    kwargs = {}
    if countdown is not None:
        kwargs["countdown"] = countdown

    process_notification_job.apply_async(
        args=[str(job_id), channel.value], queue=queue_for_channel(channel), **kwargs
    )
