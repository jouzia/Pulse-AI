"""add dashboard-supporting indexes

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-09

Two indexes, each backing a specific Phase 5 dashboard query -- not
added speculatively:

- notification_jobs(channel, status): backs GET /api/v1/ops/overview's
  grouped count query, which the dashboard polls periodically.
- dead_letter_jobs(failed_at): backs GET /api/v1/dead-letter's ordering
  (failed_at desc) and pagination.
"""

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_jobs_channel_status", "notification_jobs", ["channel", "status"]
    )
    op.create_index("ix_dead_letter_failed_at", "dead_letter_jobs", ["failed_at"])


def downgrade() -> None:
    op.drop_index("ix_dead_letter_failed_at", table_name="dead_letter_jobs")
    op.drop_index("ix_jobs_channel_status", table_name="notification_jobs")
