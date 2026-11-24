"""Exam date on courses; push subscriptions and the reminder hour; a free sample of questions
on listings; discount codes.

No course shows a free sample (preview_count 0) until its author chooses one: nothing is
shown that wasn't before.

Revision ID: 7a2b4d9c1e65
Revises: 6f1a3c8b0d54
Create Date: 2026-11-11 23:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "7a2b4d9c1e65"
down_revision: Union[str, Sequence[str], None] = "6f1a3c8b0d54"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("courses", sa.Column("exam_date", sa.Date(), nullable=True))
    op.add_column(
        "users", sa.Column("reminder_hour", sa.Integer(), nullable=True, server_default="18")
    )
    op.add_column("users", sa.Column("last_reminded_on", sa.Date(), nullable=True))
    op.add_column(
        "marketplace_listings",
        sa.Column("preview_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "marketplace_orders", sa.Column("discount_code", sa.String(length=40), nullable=True)
    )
    op.create_table(
        "push_subscriptions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("endpoint", sa.String(length=1000), nullable=False),
        sa.Column("p256dh", sa.String(length=200), nullable=False),
        sa.Column("auth", sa.String(length=100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_push_subscriptions_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_push_subscriptions")),
        sa.UniqueConstraint("endpoint", name=op.f("uq_push_subscriptions_endpoint")),
    )
    op.create_index(
        op.f("ix_push_subscriptions_user_id"), "push_subscriptions", ["user_id"], unique=False
    )
    op.create_table(
        "marketplace_discounts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("listing_id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=40), nullable=False),
        sa.Column("percent_off", sa.Integer(), nullable=False),
        sa.Column("max_uses", sa.Integer(), nullable=True),
        sa.Column("used_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "percent_off BETWEEN 1 AND 90", name=op.f("ck_marketplace_discounts_percent_range")
        ),
        sa.ForeignKeyConstraint(
            ["listing_id"],
            ["marketplace_listings.id"],
            name=op.f("fk_marketplace_discounts_listing_id_marketplace_listings"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_marketplace_discounts")),
        sa.UniqueConstraint(
            "listing_id", "code", name=op.f("uq_marketplace_discounts_listing_id_code")
        ),
    )
    op.create_index(
        op.f("ix_marketplace_discounts_listing_id"),
        "marketplace_discounts",
        ["listing_id"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_marketplace_discounts_listing_id"), table_name="marketplace_discounts")
    op.drop_table("marketplace_discounts")
    op.drop_index(op.f("ix_push_subscriptions_user_id"), table_name="push_subscriptions")
    op.drop_table("push_subscriptions")
    with op.batch_alter_table("marketplace_orders") as batch:
        batch.drop_column("discount_code")
    with op.batch_alter_table("marketplace_listings") as batch:
        batch.drop_column("preview_count")
    with op.batch_alter_table("users") as batch:
        batch.drop_column("last_reminded_on")
        batch.drop_column("reminder_hour")
    with op.batch_alter_table("courses") as batch:
        batch.drop_column("exam_date")
