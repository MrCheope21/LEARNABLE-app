"""drawing answers: item answer format and reference drawing, answer drawing

Revision ID: e5b9d2c4a713
Revises: c7d3e1a2f8b4
Create Date: 2026-10-04 14:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e5b9d2c4a713"
down_revision: Union[str, Sequence[str], None] = "c7d3e1a2f8b4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "learning_items",
        sa.Column("answer_format", sa.String(length=16), server_default="TEXT", nullable=False),
    )
    op.add_column(
        "learning_items", sa.Column("reference_drawing_type", sa.String(length=32), nullable=True)
    )
    op.add_column("answers", sa.Column("drawing_type", sa.String(length=32), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("answers", "drawing_type")
    op.drop_column("learning_items", "reference_drawing_type")
    op.drop_column("learning_items", "answer_format")
