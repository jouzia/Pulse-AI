from datetime import datetime

from pydantic import BaseModel


class OpsOverviewResponse(BaseModel):
    """
    JSON-friendly dashboard summary. Deliberately separate from /metrics
    (Prometheus text exposition format) -- this endpoint exists because
    the frontend needs structured JSON, not a Prometheus text parser.
    /metrics remains the source of truth for actual monitoring tools.

    in_process_counters_note explains, in the response itself, that the
    counter fields reset on API process restart -- the dashboard should
    surface this note rather than let a low number after a restart be
    misread as "not much traffic."
    """

    events_by_status: dict[str, int]
    jobs_by_channel_and_status: dict[str, dict[str, int]]
    dead_letter_count: int
    rate_limit_denied_total: float
    rate_limit_denied_by_channel: dict[str, float]
    configured_rate_limits_per_minute: dict[str, int]
    in_process_counters_note: str = (
        "Counter fields reflect this API process's in-memory Prometheus "
        "counters and reset to zero on restart -- they are not a durable "
        "historical total. Database-derived fields (events_by_status, "
        "jobs_by_channel_and_status, dead_letter_count) are not affected "
        "by process restarts."
    )


class DeliveryAttempt(BaseModel):
    provider: str
    provider_message_id: str | None
    status: str
    attempted_at: datetime
    delivered_at: datetime | None
    error_message: str | None

    model_config = {"from_attributes": True}


class JobDetailResponse(BaseModel):
    job_id: str
    event_id: str
    channel: str
    status: str
    attempt_count: int
    max_attempts: int
    recipient: str
    scheduled_at: datetime | None
    claimed_at: datetime | None
    lease_expires_at: datetime | None
    created_at: datetime
    updated_at: datetime
    last_error: str | None
    deliveries: list[DeliveryAttempt]


class DeadLetterItem(BaseModel):
    id: str
    original_job_id: str
    event_id: str
    channel: str
    reason: str
    attempt_count: int
    failed_at: datetime
    resolved_at: datetime | None


class DeadLetterListResponse(BaseModel):
    items: list[DeadLetterItem]
    page: int
    page_size: int
    total: int


class DeadLetterRetryResponse(BaseModel):
    job_id: str
    event_id: str
    channel: str
    status: str
