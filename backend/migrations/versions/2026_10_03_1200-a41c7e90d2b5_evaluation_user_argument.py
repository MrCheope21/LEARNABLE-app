"""evaluation user argument (second opinions)

Revision ID: a41c7e90d2b5
Revises: 81d649d3608f
Create Date: 2026-10-03 12:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a41c7e90d2b5"
down_revision: Union[str, Sequence[str], None] = "81d649d3608f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("evaluations", sa.Column("user_argument", sa.String(length=1000), nullable=True))
    op.create_index(
        "ix_evaluations_course_id_created_at", "evaluations", ["course_id", "created_at"]
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_evaluations_course_id_created_at", table_name="evaluations")
    op.drop_column("evaluations", "user_argument")
