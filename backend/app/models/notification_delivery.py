import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum as SAEnum, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.states import DeliveryStatus, enum_values
from app.db.base import Base


class NotificationDelivery(Base):
    """
    One row per provider dispatch attempt for a job. A job that retries
    3 times has 3 delivery rows — this is what makes the attempt history
    (and provider-side message id, for reconciling with a real provider's
    webhook later) auditable without reconstructing it from logs.
    """

    __tablename__ = "notification_deliveries"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("notification_jobs.id", ondelete="CASCADE"),
        nullable=False,
    )
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    provider_message_id: Mapped[str | None] = mapped_column(String(256), nullable=True)
    status: Mapped[DeliveryStatus] = mapped_column(
        SAEnum(
            DeliveryStatus,
            name="delivery_status",
            native_enum=True,
            values_callable=enum_values,
        ),
        nullable=False,
        default=DeliveryStatus.ATTEMPTED,
    )
    attempted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    delivered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    error_message: Mapped[str | None] = mapped_column(String, nullable=True)

    __table_args__ = (Index("ix_deliveries_job_id", "job_id"),)
