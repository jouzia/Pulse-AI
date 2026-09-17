"""
Read-only aggregation queries backing the operations dashboard
(app/api/v1/ops.py). Deliberately separate from event_service.py: these
are dashboard-shaped read models, not part of the core event-creation/
idempotency logic, and mixing the two would blur that boundary.
"""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import metrics
from app.core.config import get_settings
from app.core.states import EventStatus, JobStatus, NotificationChannel
from app.models.dead_letter_job import DeadLetterJob
from app.models.event import Event
from app.models.notification_job import NotificationJob
from app.schemas.ops import OpsOverviewResponse


async def get_overview(db: AsyncSession) -> OpsOverviewResponse:
    event_status_rows = (
        await db.execute(select(Event.status, func.count()).group_by(Event.status))
    ).all()
    event_counts = {status.value: 0 for status in EventStatus}
    for status, count in event_status_rows:
        event_counts[status.value] = count

    job_rows = (
        await db.execute(
            select(NotificationJob.channel, NotificationJob.status, func.count()).group_by(
                NotificationJob.channel, NotificationJob.status
            )
        )
    ).all()
    job_counts: dict[str, dict[str, int]] = {
        channel.value: {status.value: 0 for status in JobStatus}
        for channel in NotificationChannel
    }
    for channel, status, count in job_rows:
        job_counts[channel.value][status.value] = count

    dead_letter_count = (
        await db.execute(select(func.count()).select_from(DeadLetterJob))
    ).scalar_one()

    settings = get_settings()

    return OpsOverviewResponse(
        events_by_status=event_counts,
        jobs_by_channel_and_status=job_counts,
        dead_letter_count=dead_letter_count,
        rate_limit_denied_total=metrics.sum_counter(metrics.rate_limit_denied_total),
        rate_limit_denied_by_channel={
            channel.value: metrics.sum_counter(
                metrics.rate_limit_denied_total, channel=channel.value
            )
            for channel in NotificationChannel
        },
        configured_rate_limits_per_minute={
            "email": settings.rate_limit_email_per_minute,
            "sms": settings.rate_limit_sms_per_minute,
            "push": settings.rate_limit_push_per_minute,
        },
    )
