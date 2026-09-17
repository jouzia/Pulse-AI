"""add job lease tracking

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-06

Adds claimed_at / lease_expires_at to notification_jobs, backing the
Phase 3 crash-recovery sweep: a job stuck in PROCESSING past its lease is
assumed to belong to a dead worker and gets requeued (see
app/workers/recovery.py).
"""

from alembic import op
import sqlalchemy as sa

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "notification_jobs",
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "notification_jobs",
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_jobs_lease_expires_at", "notification_jobs", ["lease_expires_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_jobs_lease_expires_at", table_name="notification_jobs")
    op.drop_column("notification_jobs", "lease_expires_at")
    op.drop_column("notification_jobs", "claimed_at")
