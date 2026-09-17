from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.core.states import EventStatus, JobStatus, NotificationChannel


class EventCreateRequest(BaseModel):
    event_id: str = Field(..., min_length=1, max_length=128)
    event_type: str = Field(..., min_length=1, max_length=128)
    recipient: str = Field(..., min_length=1, max_length=256)
    channels: list[NotificationChannel] = Field(..., min_length=1)
    data: dict = Field(default_factory=dict)

    @field_validator("channels")
    @classmethod
    def channels_must_be_unique(
        cls, channels: list[NotificationChannel]
    ) -> list[NotificationChannel]:
        if len(set(channels)) != len(channels):
            raise ValueError("channels must not contain duplicates")
        return channels


class JobSummary(BaseModel):
    job_id: str
    channel: NotificationChannel
    status: JobStatus
    attempt_count: int

    model_config = {"from_attributes": True}


class EventResponse(BaseModel):
    event_id: str
    event_type: str
    status: EventStatus
    created_at: datetime
    jobs: list[JobSummary]

    model_config = {"from_attributes": True}


class EventListItem(BaseModel):
    event_id: str
    event_type: str
    status: EventStatus
    created_at: datetime

    model_config = {"from_attributes": True}


class EventListResponse(BaseModel):
    items: list[EventListItem]
    page: int
    page_size: int
    total: int
