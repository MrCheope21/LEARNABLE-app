"""Friend requests (replacing one-way follows), blocks, messages, notifications; marketplace
reviews, update notes and orders; payout and email preferences on users.

Existing follows become friendships: two people who followed each other are friends, a one-way
follow becomes a pending request from the follower.

Revision ID: 5e0f2b7a9c43
Revises: 4d9e1a6f8b32
Create Date: 2026-11-10 22:59:52.075556

"""

import uuid
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "5e0f2b7a9c43"
down_revision: Union[str, Sequence[str], None] = "4d9e1a6f8b32"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "blocks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("blocker_id", sa.Uuid(), nullable=False),
        sa.Column("blocked_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("blocker_id <> blocked_id", name=op.f("ck_blocks_not_self")),
        sa.ForeignKeyConstraint(
            ["blocked_id"],
            ["users.id"],
            name=op.f("fk_blocks_blocked_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["blocker_id"],
            ["users.id"],
            name=op.f("fk_blocks_blocker_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_blocks")),
        sa.UniqueConstraint(
            "blocker_id", "blocked_id", name=op.f("uq_blocks_blocker_id_blocked_id")
        ),
    )
    with op.batch_alter_table("blocks", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_blocks_blocked_id"), ["blocked_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_blocks_blocker_id"), ["blocker_id"], unique=False)

    op.create_table(
        "friendships",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("pair_key", sa.String(length=65), nullable=False),
        sa.Column("requester_id", sa.Uuid(), nullable=False),
        sa.Column("addressee_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("responded_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("requester_id <> addressee_id", name=op.f("ck_friendships_not_self")),
        sa.ForeignKeyConstraint(
            ["addressee_id"],
            ["users.id"],
            name=op.f("fk_friendships_addressee_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["requester_id"],
            ["users.id"],
            name=op.f("fk_friendships_requester_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_friendships")),
        sa.UniqueConstraint("pair_key", name=op.f("uq_friendships_pair_key")),
    )
    with op.batch_alter_table("friendships", schema=None) as batch_op:
        batch_op.create_index(
            "ix_friendships_addressee_id_status", ["addressee_id", "status"], unique=False
        )
        batch_op.create_index(
            "ix_friendships_requester_id_status", ["requester_id", "status"], unique=False
        )

    op.create_table(
        "messages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("pair_key", sa.String(length=65), nullable=False),
        sa.Column("sender_id", sa.Uuid(), nullable=False),
        sa.Column("recipient_id", sa.Uuid(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["recipient_id"],
            ["users.id"],
            name=op.f("fk_messages_recipient_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["sender_id"],
            ["users.id"],
            name=op.f("fk_messages_sender_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_messages")),
    )
    with op.batch_alter_table("messages", schema=None) as batch_op:
        batch_op.create_index(
            "ix_messages_pair_key_created_at", ["pair_key", "created_at"], unique=False
        )
        batch_op.create_index(
            "ix_messages_recipient_id_read_at", ["recipient_id", "read_at"], unique=False
        )
        batch_op.create_index(batch_op.f("ix_messages_sender_id"), ["sender_id"], unique=False)

    op.create_table(
        "notifications",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=True),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.Column("link", sa.String(length=300), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["actor_id"],
            ["users.id"],
            name=op.f("fk_notifications_actor_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_notifications_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_notifications")),
    )
    with op.batch_alter_table("notifications", schema=None) as batch_op:
        batch_op.create_index(
            "ix_notifications_user_id_created_at", ["user_id", "created_at"], unique=False
        )

    op.create_table(
        "marketplace_orders",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("listing_id", sa.Uuid(), nullable=False),
        sa.Column("buyer_id", sa.Uuid(), nullable=False),
        sa.Column("seller_id", sa.Uuid(), nullable=True),
        sa.Column("amount_cents", sa.Integer(), nullable=False),
        sa.Column("fee_cents", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("provider", sa.String(length=16), nullable=False),
        sa.Column("provider_session_id", sa.String(length=255), nullable=True),
        sa.Column("provider_payment_id", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("refunded_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["buyer_id"],
            ["users.id"],
            name=op.f("fk_marketplace_orders_buyer_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["listing_id"],
            ["marketplace_listings.id"],
            name=op.f("fk_marketplace_orders_listing_id_marketplace_listings"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["seller_id"],
            ["users.id"],
            name=op.f("fk_marketplace_orders_seller_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_marketplace_orders")),
        sa.UniqueConstraint(
            "provider_session_id", name=op.f("uq_marketplace_orders_provider_session_id")
        ),
    )
    with op.batch_alter_table("marketplace_orders", schema=None) as batch_op:
        batch_op.create_index(
            "ix_marketplace_orders_buyer_id_listing_id", ["buyer_id", "listing_id"], unique=False
        )
        batch_op.create_index(
            "ix_marketplace_orders_seller_id_status", ["seller_id", "status"], unique=False
        )

    op.create_table(
        "marketplace_reviews",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("listing_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("rating", sa.Integer(), nullable=False),
        sa.Column("comment", sa.Text(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("reply", sa.Text(), server_default="", nullable=False),
        sa.Column("replied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "rating BETWEEN 1 AND 5", name=op.f("ck_marketplace_reviews_rating_range")
        ),
        sa.ForeignKeyConstraint(
            ["listing_id"],
            ["marketplace_listings.id"],
            name=op.f("fk_marketplace_reviews_listing_id_marketplace_listings"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_marketplace_reviews_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_marketplace_reviews")),
        sa.UniqueConstraint(
            "listing_id", "user_id", name=op.f("uq_marketplace_reviews_listing_id_user_id")
        ),
    )
    with op.batch_alter_table("marketplace_reviews", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_marketplace_reviews_listing_id"), ["listing_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_marketplace_reviews_user_id"), ["user_id"], unique=False
        )

    op.create_table(
        "marketplace_updates",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("listing_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=True),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("recipients", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["listing_id"],
            ["marketplace_listings.id"],
            name=op.f("fk_marketplace_updates_listing_id_marketplace_listings"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_marketplace_updates")),
    )
    with op.batch_alter_table("marketplace_updates", schema=None) as batch_op:
        batch_op.create_index(
            "ix_marketplace_updates_listing_id_created_at",
            ["listing_id", "created_at"],
            unique=False,
        )

    _follows_to_friendships()
    with op.batch_alter_table("follows", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_follows_followee_id"))
        batch_op.drop_index(batch_op.f("ix_follows_follower_id"))

    op.drop_table("follows")
    with op.batch_alter_table("marketplace_listings", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("rating_count", sa.Integer(), server_default="0", nullable=False)
        )
        batch_op.add_column(
            sa.Column("rating_sum", sa.Integer(), server_default="0", nullable=False)
        )

    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("email_updates", sa.Boolean(), server_default=sa.true(), nullable=False)
        )
        batch_op.add_column(sa.Column("payout_account_id", sa.String(length=255), nullable=True))
        batch_op.add_column(
            sa.Column("payout_ready", sa.Boolean(), server_default=sa.false(), nullable=False)
        )


def _follows_to_friendships() -> None:
    bind = op.get_bind()
    # Typed columns, so ids and dates are read the way each database stores them.
    follows = sa.table(
        "follows",
        sa.column("follower_id", sa.Uuid()),
        sa.column("followee_id", sa.Uuid()),
        sa.column("created_at", sa.DateTime(timezone=True)),
    )
    rows = bind.execute(
        sa.select(follows.c.follower_id, follows.c.followee_id, follows.c.created_at).order_by(
            follows.c.created_at
        )
    ).all()
    seen: dict[str, dict[str, object]] = {}
    for follower, followee, created_at in rows:
        a, b = follower, followee
        key = ":".join(sorted((a.hex, b.hex)))
        if key in seen:
            # The other one followed back: they are friends.
            seen[key]["status"] = "ACCEPTED"
            seen[key]["responded_at"] = created_at
        else:
            seen[key] = {
                "id": uuid.uuid4(),
                "pair_key": key,
                "requester_id": a,
                "addressee_id": b,
                "status": "PENDING",
                "created_at": created_at,
                "responded_at": None,
            }
    if seen:
        friendships = sa.table(
            "friendships",
            sa.column("id", sa.Uuid()),
            sa.column("pair_key", sa.String()),
            sa.column("requester_id", sa.Uuid()),
            sa.column("addressee_id", sa.Uuid()),
            sa.column("status", sa.String()),
            sa.column("created_at", sa.DateTime(timezone=True)),
            sa.column("responded_at", sa.DateTime(timezone=True)),
        )
        op.bulk_insert(friendships, list(seen.values()))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_column("payout_ready")
        batch_op.drop_column("payout_account_id")
        batch_op.drop_column("email_updates")

    with op.batch_alter_table("marketplace_listings", schema=None) as batch_op:
        batch_op.drop_column("rating_sum")
        batch_op.drop_column("rating_count")

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
    with op.batch_alter_table("follows", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_follows_follower_id"), ["follower_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_follows_followee_id"), ["followee_id"], unique=False)

    with op.batch_alter_table("marketplace_updates", schema=None) as batch_op:
        batch_op.drop_index("ix_marketplace_updates_listing_id_created_at")

    op.drop_table("marketplace_updates")
    with op.batch_alter_table("marketplace_reviews", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_marketplace_reviews_user_id"))
        batch_op.drop_index(batch_op.f("ix_marketplace_reviews_listing_id"))

    op.drop_table("marketplace_reviews")
    with op.batch_alter_table("marketplace_orders", schema=None) as batch_op:
        batch_op.drop_index("ix_marketplace_orders_seller_id_status")
        batch_op.drop_index("ix_marketplace_orders_buyer_id_listing_id")

    op.drop_table("marketplace_orders")
    with op.batch_alter_table("notifications", schema=None) as batch_op:
        batch_op.drop_index("ix_notifications_user_id_created_at")

    op.drop_table("notifications")
    with op.batch_alter_table("messages", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_messages_sender_id"))
        batch_op.drop_index("ix_messages_recipient_id_read_at")
        batch_op.drop_index("ix_messages_pair_key_created_at")

    op.drop_table("messages")
    with op.batch_alter_table("friendships", schema=None) as batch_op:
        batch_op.drop_index("ix_friendships_requester_id_status")
        batch_op.drop_index("ix_friendships_addressee_id_status")

    op.drop_table("friendships")
    with op.batch_alter_table("blocks", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_blocks_blocker_id"))
        batch_op.drop_index(batch_op.f("ix_blocks_blocked_id"))

    op.drop_table("blocks")
