"""course archive: courses can be put away without deleting them

Revision ID: c5e9a3b7d1f4
Revises: b4d8f2a6c0e3
Create Date: 2026-10-05 22:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c5e9a3b7d1f4"
down_revision: Union[str, Sequence[str], None] = "b4d8f2a6c0e3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("courses", sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("courses", "archived_at")
