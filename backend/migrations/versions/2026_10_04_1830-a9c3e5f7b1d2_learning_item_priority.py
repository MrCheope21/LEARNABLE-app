"""learning item priority (1 Essential, 2 Important, 3 Extra)

Revision ID: a9c3e5f7b1d2
Revises: f2a8c6d1e9b0
Create Date: 2026-10-04 18:30:00.000000

Existing items start from their AI-suggested role, as new generated items do.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a9c3e5f7b1d2"
down_revision: Union[str, Sequence[str], None] = "f2a8c6d1e9b0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "learning_items", sa.Column("priority", sa.Integer(), server_default="2", nullable=False)
    )
    op.execute("UPDATE learning_items SET priority = 1 WHERE role = 'CORE_TRAINABLE'")
    op.execute(
        "UPDATE learning_items SET priority = 3 "
        "WHERE role IN ('INFORMATIONAL', 'REFERENCE', 'OPTIONAL_EXTENSION')"
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("learning_items", "priority")
