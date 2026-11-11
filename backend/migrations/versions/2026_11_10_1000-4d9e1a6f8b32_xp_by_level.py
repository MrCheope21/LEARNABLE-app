"""XP follows the item's level: the award records the level it was decided at.

Revision ID: 4d9e1a6f8b32
Revises: 3c8d0f5e7a21
Create Date: 2026-11-10 10:00:00
"""

import sqlalchemy as sa
from alembic import op

revision = "4d9e1a6f8b32"
down_revision = "3c8d0f5e7a21"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("xp_awards") as batch:
        batch.add_column(sa.Column("level", sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("xp_awards") as batch:
        batch.drop_column("level")
