"""add updated_version_id and order_index to task

Revision ID: 63ace278c0e6
Revises: 68c60f4de304
Create Date: 2025-02-02 09:58:31.395643

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "63ace278c0e6"
down_revision: str | None = "68c60f4de304"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column("task", sa.Column("updated_version_id", sa.Integer(), nullable=True))
    op.add_column("task", sa.Column("order_index", sa.Integer(), nullable=False))
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column("task", "order_index")
    op.drop_column("task", "updated_version_id")
    # ### end Alembic commands ###
