"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-09-05

Creates the five Phase 1 tables and their native Postgres enum types.
Enum values here are hardcoded strings (not imported from app.core.states)
deliberately: migrations are a historical record and must stay stable even
if the Python enum's members are ever renumbered or refactored later —
importing app code into a migration couples migration history to
application code that can change out from under it.

Critical invariants enforced at the DATABASE level, not in application
code:
  - events.event_id UNIQUE            (uq_events_event_id)
  - notification_jobs(event_id, channel) UNIQUE  (uq_job_event_channel)
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels = None
depends_on = None

# create_type=False on every enum here: Postgres ENUM columns normally
# attach their own before_create/after_drop DDL events to auto-manage the
# type, which would race with the explicit .create()/.drop() calls below.
# Disabling it makes the explicit calls the only thing that ever creates
# or drops these types.
event_status_enum = postgresql.ENUM(
    "received",
    "validated",
    "queued",
    "processing",
    "delivered",
    "failed",
    "dead_lettered",
    name="event_status",
    create_type=False,
)
job_status_enum = postgresql.ENUM(
    "pending",
    "queued",
    "processing",
    "delivered",
    "failed",
    "retrying",
    "dead_lettered",
    name="job_status",
    create_type=False,
)
delivery_status_enum = postgresql.ENUM(
    "attempted",
    "delivered",
    "failed",
    name="delivery_status",
    create_type=False,
)
notification_channel_enum = postgresql.ENUM(
    "email",
    "sms",
    "push",
    name="notification_channel",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    event_status_enum.create(bind, checkfirst=True)
    job_status_enum.create(bind, checkfirst=True)
    delivery_status_enum.create(bind, checkfirst=True)
    notification_channel_enum.create(bind, checkfirst=True)

    op.create_table(
        "events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("event_id", sa.String(length=128), nullable=False),
        sa.Column("event_type", sa.String(length=128), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column(
            "status", event_status_enum, nullable=False, server_default="received"
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("event_id", name="uq_events_event_id"),
    )
    op.create_index("ix_events_event_type", "events", ["event_type"])
    op.create_index("ix_events_status", "events", ["status"])

    op.create_table(
        "notification_templates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("channel", notification_channel_enum, nullable=False),
        sa.Column("subject", sa.String(length=256), nullable=True),
        sa.Column("body", sa.String(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("name", "channel", "version", name="uq_template_version"),
    )

    op.create_table(
        "notification_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "event_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("events.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("recipient", sa.String(length=256), nullable=False),
        sa.Column("channel", notification_channel_enum, nullable=False),
        sa.Column(
            "template_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("notification_templates.id"),
            nullable=True,
        ),
        sa.Column(
            "status", job_status_enum, nullable=False, server_default="pending"
        ),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("event_id", "channel", name="uq_job_event_channel"),
    )
    op.create_index("ix_jobs_status", "notification_jobs", ["status"])
    op.create_index("ix_jobs_scheduled_at", "notification_jobs", ["scheduled_at"])

    op.create_table(
        "notification_deliveries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "job_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("notification_jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("provider_message_id", sa.String(length=256), nullable=True),
        sa.Column(
            "status",
            delivery_status_enum,
            nullable=False,
            server_default="attempted",
        ),
        sa.Column(
            "attempted_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.String(), nullable=True),
    )
    op.create_index("ix_deliveries_job_id", "notification_deliveries", ["job_id"])

    op.create_table(
        "dead_letter_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "original_job_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("notification_jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("reason", sa.String(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column(
            "failed_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("dead_letter_jobs")
    op.drop_index("ix_deliveries_job_id", table_name="notification_deliveries")
    op.drop_table("notification_deliveries")
    op.drop_index("ix_jobs_scheduled_at", table_name="notification_jobs")
    op.drop_index("ix_jobs_status", table_name="notification_jobs")
    op.drop_table("notification_jobs")
    op.drop_table("notification_templates")
    op.drop_index("ix_events_status", table_name="events")
    op.drop_index("ix_events_event_type", table_name="events")
    op.drop_table("events")

    bind = op.get_bind()
    notification_channel_enum.drop(bind, checkfirst=True)
    delivery_status_enum.drop(bind, checkfirst=True)
    job_status_enum.drop(bind, checkfirst=True)
    event_status_enum.drop(bind, checkfirst=True)
