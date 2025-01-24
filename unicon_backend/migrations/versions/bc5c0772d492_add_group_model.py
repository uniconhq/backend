"""add group model

Revision ID: bc5c0772d492
Revises: 68c60f4de304
Create Date: 2025-01-25 00:03:35.171604

"""

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "bc5c0772d492"
down_revision: str | None = "68c60f4de304"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table(
        "group",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_group")),
    )
    op.create_table(
        "group_member",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("group_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["group_id"], ["group.id"], name=op.f("fk_group_member_group_id_group")
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["user.id"], name=op.f("fk_group_member_user_id_user")
        ),
        sa.PrimaryKeyConstraint("user_id", "group_id", name=op.f("pk_group_member")),
    )
    op.create_table(
        "group_supervisor",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("group_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["group_id"], ["group.id"], name=op.f("fk_group_supervisor_group_id_group")
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["user.id"], name=op.f("fk_group_supervisor_user_id_user")
        ),
        sa.PrimaryKeyConstraint("user_id", "group_id", name=op.f("pk_group_supervisor")),
    )
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_table("group_supervisor")
    op.drop_table("group_member")
    op.drop_table("group")
    # ### end Alembic commands ###
