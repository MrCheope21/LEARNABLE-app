"""Tags a user follows (a notification when a course carrying one is first published) and
reports to the administrator about a person, a message or a review.

Revision ID: 6f1a3c8b0d54
Revises: 5e0f2b7a9c43
Create Date: 2026-11-11 10:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "6f1a3c8b0d54"
down_revision: Union[str, Sequence[str], None] = "5e0f2b7a9c43"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "tag_subscriptions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("tag", sa.String(length=40), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_tag_subscriptions_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tag_subscriptions")),
        sa.UniqueConstraint("user_id", "tag", name=op.f("uq_tag_subscriptions_user_id_tag")),
    )
    op.create_index(
        op.f("ix_tag_subscriptions_user_id"), "tag_subscriptions", ["user_id"], unique=False
    )
    op.create_index(op.f("ix_tag_subscriptions_tag"), "tag_subscriptions", ["tag"], unique=False)
    op.create_table(
        "reports",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("reporter_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("target_id", sa.Uuid(), nullable=False),
        sa.Column("subject_id", sa.Uuid(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("excerpt", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["reporter_id"],
            ["users.id"],
            name=op.f("fk_reports_reporter_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["subject_id"],
            ["users.id"],
            name=op.f("fk_reports_subject_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_reports")),
        sa.UniqueConstraint(
            "reporter_id",
            "kind",
            "target_id",
            name=op.f("uq_reports_reporter_id_kind_target_id"),
        ),
    )
    op.create_index(op.f("ix_reports_reporter_id"), "reports", ["reporter_id"], unique=False)
    op.create_index("ix_reports_status_created_at", "reports", ["status", "created_at"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_reports_status_created_at", table_name="reports")
    op.drop_index(op.f("ix_reports_reporter_id"), table_name="reports")
    op.drop_table("reports")
    op.drop_index(op.f("ix_tag_subscriptions_tag"), table_name="tag_subscriptions")
    op.drop_index(op.f("ix_tag_subscriptions_user_id"), table_name="tag_subscriptions")
    op.drop_table("tag_subscriptions")
