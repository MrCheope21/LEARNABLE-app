"""A picture shown with a question (learning_items.question_image_type).

Revision ID: ae5f7b2c4d98
Revises: 9d4e6f1a3b87
Create Date: 2026-11-24 10:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "ae5f7b2c4d98"
down_revision: Union[str, Sequence[str], None] = "9d4e6f1a3b87"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "learning_items", sa.Column("question_image_type", sa.String(length=32), nullable=True)
    )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("learning_items") as batch:
        batch.drop_column("question_image_type")
