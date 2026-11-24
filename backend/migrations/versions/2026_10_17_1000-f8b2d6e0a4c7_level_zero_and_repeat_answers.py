"""level zero relearning (policy v3) and evaluated repeats

Revision ID: f8b2d6e0a4c7
Revises: e7a1c5d9f3b6
Create Date: 2026-10-17 10:00:00.000000

Items move to scheduling policy chessable v3 (a failed review goes back to level 0) at once;
their history rows keep the version that produced them. A repeat of an answer is stored as an
answer of its own, pointing at the one it repeats.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f8b2d6e0a4c7"
down_revision: Union[str, Sequence[str], None] = "e7a1c5d9f3b6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema and data."""
    op.add_column("answers", sa.Column("repeat_of_id", sa.Uuid(), nullable=True))
    op.create_index(op.f("ix_answers_repeat_of_id"), "answers", ["repeat_of_id"])
    op.execute(
        "UPDATE review_states SET scheduling_policy_version = '3' "
        "WHERE scheduling_policy = 'chessable' AND scheduling_policy_version IN ('1', '2')"
    )


def downgrade() -> None:
    """Downgrade schema and data."""
    op.execute(
        "UPDATE review_states SET scheduling_policy_version = '2' "
        "WHERE scheduling_policy = 'chessable' AND scheduling_policy_version = '3'"
    )
    op.drop_index(op.f("ix_answers_repeat_of_id"), table_name="answers")
    op.drop_column("answers", "repeat_of_id")
