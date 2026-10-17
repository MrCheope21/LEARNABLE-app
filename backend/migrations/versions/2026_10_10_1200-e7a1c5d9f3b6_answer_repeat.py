"""answer repeat: review the reference answer and repeat a mostly green answer

Revision ID: e7a1c5d9f3b6
Revises: d6f0b4c8e2a5
Create Date: 2026-10-10 12:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e7a1c5d9f3b6"
down_revision: Union[str, Sequence[str], None] = "d6f0b4c8e2a5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "answers",
        sa.Column("repeat_offered", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.add_column("answers", sa.Column("repeat_text", sa.Text(), nullable=True))
    op.add_column("answers", sa.Column("repeated_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("answers", "repeated_at")
    op.drop_column("answers", "repeat_text")
    op.drop_column("answers", "repeat_offered")
