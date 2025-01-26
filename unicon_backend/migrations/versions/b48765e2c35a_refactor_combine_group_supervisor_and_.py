"""refactor: combine group supervisor and member

Revision ID: b48765e2c35a
Revises: 2b103945f96c
Create Date: 2025-01-26 13:16:34.486564

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b48765e2c35a"
down_revision: str | None = "2b103945f96c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_table("group_supervisor")
    op.add_column(
        "group_member", sa.Column("is_supervisor", sa.Boolean(), server_default="0", nullable=False)
    )
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column("group_member", "is_supervisor")
    op.create_table(
        "group_supervisor",
        sa.Column("user_id", sa.INTEGER(), autoincrement=False, nullable=False),
        sa.Column("group_id", sa.INTEGER(), autoincrement=False, nullable=False),
        sa.ForeignKeyConstraint(
            ["group_id"], ["group.id"], name="fk_group_supervisor_group_id_group"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], name="fk_group_supervisor_user_id_user"),
        sa.PrimaryKeyConstraint("user_id", "group_id", name="pk_group_supervisor"),
    )
    # ### end Alembic commands ###
