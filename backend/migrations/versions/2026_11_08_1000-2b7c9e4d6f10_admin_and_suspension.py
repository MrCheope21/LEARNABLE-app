"""administrators and suspended accounts

Revision ID: 2b7c9e4d6f10
Revises: 1d4e7a9c2b58
Create Date: 2026-11-08 10:00:00.000000

Every existing account stays active and is not an administrator.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "2b7c9e4d6f10"
down_revision: Union[str, Sequence[str], None] = "1d4e7a9c2b58"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("users") as batch:
        batch.add_column(
            sa.Column("is_admin", sa.Boolean(), server_default=sa.false(), nullable=False)
        )
        batch.add_column(
            sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False)
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("users") as batch:
        batch.drop_column("is_active")
        batch.drop_column("is_admin")
