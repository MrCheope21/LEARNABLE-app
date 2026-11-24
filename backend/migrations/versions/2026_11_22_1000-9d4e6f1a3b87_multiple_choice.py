"""Multiple-choice questions: the options of an item (answer_format CHOICE).

Revision ID: 9d4e6f1a3b87
Revises: 8c3d5e0f2a76
Create Date: 2026-11-22 10:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9d4e6f1a3b87"
down_revision: Union[str, Sequence[str], None] = "8c3d5e0f2a76"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("learning_items", sa.Column("choices", sa.JSON(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("learning_items") as batch:
        batch.drop_column("choices")
