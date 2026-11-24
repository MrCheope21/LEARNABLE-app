"""community: opt-in visibility and following

Revision ID: d6f0b4c8e2a5
Revises: c5e9a3b7d1f4
Create Date: 2026-10-10 10:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d6f0b4c8e2a5"
down_revision: Union[str, Sequence[str], None] = "c5e9a3b7d1f4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "users",
        sa.Column("community_visible", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.create_table(
        "follows",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("follower_id", sa.Uuid(), nullable=False),
        sa.Column("followee_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("follower_id <> followee_id", name=op.f("ck_follows_not_self")),
        sa.ForeignKeyConstraint(
            ["followee_id"],
            ["users.id"],
            name=op.f("fk_follows_followee_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["follower_id"],
            ["users.id"],
            name=op.f("fk_follows_follower_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_follows")),
        sa.UniqueConstraint(
            "follower_id", "followee_id", name=op.f("uq_follows_follower_id_followee_id")
        ),
    )
    op.create_index(op.f("ix_follows_followee_id"), "follows", ["followee_id"])
    op.create_index(op.f("ix_follows_follower_id"), "follows", ["follower_id"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_follows_follower_id"), table_name="follows")
    op.drop_index(op.f("ix_follows_followee_id"), table_name="follows")
    op.drop_table("follows")
    op.drop_column("users", "community_visible")
