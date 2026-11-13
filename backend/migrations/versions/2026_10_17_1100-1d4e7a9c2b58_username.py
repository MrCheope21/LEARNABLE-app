"""optional username to sign in with

Revision ID: 1d4e7a9c2b58
Revises: f8b2d6e0a4c7
Create Date: 2026-10-17 11:00:00.000000

A unique, lowercase sign-in name, an alternative to the email. Existing accounts have none.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "1d4e7a9c2b58"
down_revision: Union[str, Sequence[str], None] = "f8b2d6e0a4c7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("username", sa.String(length=30), nullable=True))
        batch.create_index(op.f("ix_users_username"), ["username"], unique=True)


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("users") as batch:
        batch.drop_index(op.f("ix_users_username"))
        batch.drop_column("username")
