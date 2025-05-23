"""add problem leaderboard fields

Revision ID: ece55a890e78
Revises: 5a36aa9e3ca6
Create Date: 2025-04-03 22:06:58.657257

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "ece55a890e78"
down_revision: str | None = "5a36aa9e3ca6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column(
        "problem",
        sa.Column("leaderboard_enabled", sa.Boolean(), server_default="false", nullable=False),
    )
    op.add_column("task", sa.Column("min_score_to_pass", sa.Integer(), nullable=True))
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column("task", "min_score_to_pass")
    op.drop_column("problem", "leaderboard_enabled")
    # ### end Alembic commands ###
