import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    Enum as SAEnum,
    Index,
    JSON,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.states import EventStatus, enum_values
from app.db.base import Base


class Event(Base):
    """
    Source-of-record for every inbound event.

    `event_id` is the caller-supplied idempotency key and is UNIQUE at the
    database level — duplicate submissions are rejected by the constraint,
    not by an application-level "if already exists" check, which would
    leave a race window under concurrent requests.
    """

    __tablename__ = "events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    event_id: Mapped[str] = mapped_column(String(128), nullable=False)
    event_type: Mapped[str] = mapped_column(String(128), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    status: Mapped[EventStatus] = mapped_column(
        SAEnum(
            EventStatus,
            name="event_status",
            native_enum=True,
            values_callable=enum_values,
        ),
        nullable=False,
        default=EventStatus.RECEIVED,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    processed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        # Named explicitly (rather than unique=True) so the constraint name
        # is stable and matches the Alembic migration and the IntegrityError
        # inspection in app/services/event_service.py.
        UniqueConstraint("event_id", name="uq_events_event_id"),
        # event_type is queried heavily on the dashboard's event-detail /
        # filter views; index it explicitly rather than relying on a scan.
        Index("ix_events_event_type", "event_type"),
        Index("ix_events_status", "status"),
    )
