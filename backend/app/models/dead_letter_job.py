import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, JSON, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class DeadLetterJob(Base):
    """
    Record of a job that exhausted its retry budget. Keeps a snapshot of
    the payload and the failure reason at time of dead-lettering, and a
    `resolved_at` timestamp that gets set when an operator triggers a
    controlled retry (POST /dead-letter/{id}/retry) rather than the
    original job silently reappearing in the normal queue.
    """

    __tablename__ = "dead_letter_jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    original_job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("notification_jobs.id", ondelete="CASCADE"),
        nullable=False,
    )
    reason: Mapped[str] = mapped_column(String, nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    failed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        # Backs GET /api/v1/dead-letter's ordering (failed_at desc) and
        # pagination (Phase 5).
        Index("ix_dead_letter_failed_at", "failed_at"),
    )
