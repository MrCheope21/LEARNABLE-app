"""move review states to scheduling policy chessable v2

Revision ID: f2a8c6d1e9b0
Revises: e5b9d2c4a713
Create Date: 2026-10-04 18:00:00.000000

Same ladder; v2 only changes how HARD and a first slip move an item (owner decision,
2026-10-04). Items move to it at once; their history rows keep the version that produced them.
"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f2a8c6d1e9b0"
down_revision: Union[str, Sequence[str], None] = "e5b9d2c4a713"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade data."""
    op.execute(
        "UPDATE review_states SET scheduling_policy_version = '2' "
        "WHERE scheduling_policy = 'chessable' AND scheduling_policy_version = '1'"
    )


def downgrade() -> None:
    """Downgrade data."""
    op.execute(
        "UPDATE review_states SET scheduling_policy_version = '1' "
        "WHERE scheduling_policy = 'chessable' AND scheduling_policy_version = '2'"
    )
