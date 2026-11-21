"""Add email signup challenges and explicit no-deadline confirmation."""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "action_items",
        sa.Column(
            "no_deadline_confirmed",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.create_table(
        "registration_tokens",
        sa.Column("token_hash", sa.String(), primary_key=True),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_registration_tokens_email", "registration_tokens", ["email"])
    op.create_index(
        "ix_registration_tokens_expires_at", "registration_tokens", ["expires_at"]
    )


def downgrade():
    raise RuntimeError(
        "Restore a pre-migration backup to return to the previous schema."
    )
