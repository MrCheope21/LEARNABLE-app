"""user language and display name

Revision ID: c7d3e1a2f8b4
Revises: a41c7e90d2b5
Create Date: 2026-10-04 10:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c7d3e1a2f8b4"
down_revision: Union[str, Sequence[str], None] = "a41c7e90d2b5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "users", sa.Column("language", sa.String(length=8), server_default="en", nullable=False)
    )
    op.add_column("users", sa.Column("display_name", sa.String(length=80), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("users", "display_name")
    op.drop_column("users", "language")
