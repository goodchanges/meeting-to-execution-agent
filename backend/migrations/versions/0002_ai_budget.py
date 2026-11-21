"""Persist aggregate AI call accounting across account deletion."""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "ai_monthly_totals",
        sa.Column("month", sa.Date(), primary_key=True),
        sa.Column("calls", sa.Integer(), nullable=False),
    )
    op.execute(
        "INSERT INTO ai_monthly_totals (month, calls) "
        "SELECT date(created_at, 'start of month'), count(*) FROM ai_usage "
        "WHERE provider <> 'demo' GROUP BY date(created_at, 'start of month')"
    )
    op.create_index(
        "ix_decisions_owner_status_updated",
        "decisions",
        ["user_id", "status", "updated_at"],
    )
    op.create_index(
        "ix_meetings_owner_sha", "meetings", ["user_id", "transcript_sha256"]
    )
    op.create_index("ix_ai_usage_owner_created", "ai_usage", ["user_id", "created_at"])


def downgrade():
    raise RuntimeError(
        "Restore a pre-migration backup to return to the previous schema."
    )
