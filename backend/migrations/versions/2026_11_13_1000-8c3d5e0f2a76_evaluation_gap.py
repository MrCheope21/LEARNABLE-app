"""Evaluations keep one sentence on what the answer lacked (answer_evaluation_v3).

Revision ID: 8c3d5e0f2a76
Revises: 7a2b4d9c1e65
Create Date: 2026-11-13 10:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "8c3d5e0f2a76"
down_revision: Union[str, Sequence[str], None] = "7a2b4d9c1e65"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("evaluations", sa.Column("gap", sa.Text(), nullable=False, server_default=""))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("evaluations") as batch:
        batch.drop_column("gap")
