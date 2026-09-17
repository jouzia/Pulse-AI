import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.states import JobStatus, NotificationChannel, enum_values
from app.db.base import Base


class NotificationJob(Base):
    """
    One row per (event, channel) pair — this is the idempotency boundary
    that matters most in practice. The unique constraint on
    (event_id, channel) means a second attempt to create the same job
    (e.g. from a retried API call, or a re-processed queue message) fails
    at the database rather than producing a duplicate send.

    Workers claim jobs with `SELECT ... FOR UPDATE SKIP LOCKED` (see
    app/workers/tasks.py) so two workers racing on the same row never both
    transition it out of QUEUED/RETRYING. `claimed_at`/`lease_expires_at`
    back the crash-recovery sweep (app/workers/recovery.py): a job stuck
    in PROCESSING past its lease is assumed to belong to a dead worker and
    is requeued.
    """

    __tablename__ = "notification_jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("events.id", ondelete="CASCADE"), nullable=False
    )
    recipient: Mapped[str] = mapped_column(String(256), nullable=False)
    channel: Mapped[NotificationChannel] = mapped_column(
        SAEnum(
            NotificationChannel,
            name="notification_channel",
            native_enum=True,
            values_callable=enum_values,
        ),
        nullable=False,
    )
    template_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("notification_templates.id"),
        nullable=True,
    )
    status: Mapped[JobStatus] = mapped_column(
        SAEnum(
            JobStatus, name="job_status", native_enum=True, values_callable=enum_values
        ),
        nullable=False,
        default=JobStatus.PENDING,
    )
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    scheduled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    processed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_error: Mapped[str | None] = mapped_column(String, nullable=True)
    claimed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint("event_id", "channel", name="uq_job_event_channel"),
        Index("ix_jobs_status", "status"),
        Index("ix_jobs_scheduled_at", "scheduled_at"),
        Index("ix_jobs_lease_expires_at", "lease_expires_at"),
        # Backs GET /api/v1/ops/overview's grouped count query (Phase 5).
        Index("ix_jobs_channel_status", "channel", "status"),
    )
