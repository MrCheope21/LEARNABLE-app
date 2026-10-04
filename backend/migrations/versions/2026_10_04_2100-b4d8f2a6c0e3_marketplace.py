"""marketplace: listings, access, and the courses that mirror them

Revision ID: b4d8f2a6c0e3
Revises: a9c3e5f7b1d2
Create Date: 2026-10-04 21:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b4d8f2a6c0e3"
down_revision: Union[str, Sequence[str], None] = "a9c3e5f7b1d2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_ORIGIN_TABLES = ("chapters", "topics", "concepts", "learning_items")


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "marketplace_listings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("author_id", sa.Uuid(), nullable=False),
        sa.Column("source_course_id", sa.Uuid(), nullable=True),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("subtitle", sa.String(length=200), server_default="", nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("outcomes", sa.JSON(), nullable=False),
        sa.Column("audience", sa.Text(), nullable=False),
        sa.Column("level", sa.String(length=16), server_default="all", nullable=False),
        sa.Column("category", sa.String(length=32), server_default="other", nullable=False),
        sa.Column("language", sa.String(length=16), nullable=False),
        sa.Column("tags", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("price_cents", sa.Integer(), server_default="0", nullable=False),
        sa.Column("currency", sa.String(length=3), server_default="EUR", nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("chapter_count", sa.Integer(), nullable=False),
        sa.Column("item_count", sa.Integer(), nullable=False),
        sa.Column("acquisition_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["author_id"],
            ["users.id"],
            name=op.f("fk_marketplace_listings_author_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["source_course_id"],
            ["courses.id"],
            name=op.f("fk_marketplace_listings_source_course_id_courses"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_marketplace_listings")),
        sa.UniqueConstraint(
            "source_course_id", name=op.f("uq_marketplace_listings_source_course_id")
        ),
    )
    op.create_index(
        op.f("ix_marketplace_listings_author_id"), "marketplace_listings", ["author_id"]
    )
    op.create_index(
        "ix_marketplace_listings_status_published_at",
        "marketplace_listings",
        ["status", "published_at"],
    )
    op.create_index(
        "ix_marketplace_listings_status_category", "marketplace_listings", ["status", "category"]
    )
    op.create_table(
        "marketplace_acquisitions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("listing_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("course_id", sa.Uuid(), nullable=True),
        sa.Column("price_cents", sa.Integer(), nullable=False),
        sa.Column("acquired_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["course_id"],
            ["courses.id"],
            name=op.f("fk_marketplace_acquisitions_course_id_courses"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["listing_id"],
            ["marketplace_listings.id"],
            name=op.f("fk_marketplace_acquisitions_listing_id_marketplace_listings"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_marketplace_acquisitions_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_marketplace_acquisitions")),
        sa.UniqueConstraint(
            "listing_id", "user_id", name=op.f("uq_marketplace_acquisitions_listing_id_user_id")
        ),
    )
    op.create_index(
        op.f("ix_marketplace_acquisitions_listing_id"), "marketplace_acquisitions", ["listing_id"]
    )
    op.create_index(
        op.f("ix_marketplace_acquisitions_user_id"), "marketplace_acquisitions", ["user_id"]
    )

    with op.batch_alter_table("courses") as batch:
        batch.add_column(sa.Column("marketplace_listing_id", sa.Uuid(), nullable=True))
        batch.add_column(sa.Column("marketplace_version", sa.Integer(), nullable=True))
        batch.create_index(
            batch.f("ix_courses_marketplace_listing_id"), ["marketplace_listing_id"]
        )
        batch.create_foreign_key(
            batch.f("fk_courses_marketplace_listing_id_marketplace_listings"),
            "marketplace_listings",
            ["marketplace_listing_id"],
            ["id"],
            ondelete="SET NULL",
        )
    for table in _ORIGIN_TABLES:
        op.add_column(table, sa.Column("origin_key", sa.String(length=32), nullable=True))
    op.add_column("learning_items", sa.Column("origin_priority", sa.Integer(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("learning_items", "origin_priority")
    for table in _ORIGIN_TABLES:
        op.drop_column(table, "origin_key")
    with op.batch_alter_table("courses") as batch:
        batch.drop_constraint(
            batch.f("fk_courses_marketplace_listing_id_marketplace_listings"), type_="foreignkey"
        )
        batch.drop_index(batch.f("ix_courses_marketplace_listing_id"))
        batch.drop_column("marketplace_version")
        batch.drop_column("marketplace_listing_id")
    op.drop_index(
        op.f("ix_marketplace_acquisitions_user_id"), table_name="marketplace_acquisitions"
    )
    op.drop_index(
        op.f("ix_marketplace_acquisitions_listing_id"), table_name="marketplace_acquisitions"
    )
    op.drop_table("marketplace_acquisitions")
    op.drop_index("ix_marketplace_listings_status_category", table_name="marketplace_listings")
    op.drop_index(
        "ix_marketplace_listings_status_published_at", table_name="marketplace_listings"
    )
    op.drop_index(op.f("ix_marketplace_listings_author_id"), table_name="marketplace_listings")
    op.drop_table("marketplace_listings")
