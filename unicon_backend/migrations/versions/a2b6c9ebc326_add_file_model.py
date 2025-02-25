"""add file model

Revision ID: a2b6c9ebc326
Revises: 04de0314e0a9
Create Date: 2025-02-25 17:19:23.549774

"""

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "a2b6c9ebc326"
down_revision: str | None = "04de0314e0a9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table(
        "file",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("path", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("parent_id", sa.Integer(), nullable=False),
        sa.Column("parent_type", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("on_minio", sa.Boolean(), nullable=False),
        sa.Column("key", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("content", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_file")),
    )
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_table("file")
    # ### end Alembic commands ###
