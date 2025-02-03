"""initialize tables

Revision ID: 412a1b074446
Revises:
Create Date: 2025-02-02 19:32:34.772030

"""

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "412a1b074446"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table(
        "user",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("username", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("password", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user")),
    )
    op.create_index(op.f("ix_user_username"), "user", ["username"], unique=True)
    op.create_table(
        "organisation",
        sa.Column("name", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("description", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("owner_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["owner_id"], ["user.id"], name=op.f("fk_organisation_owner_id_user")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_organisation")),
    )
    op.create_table(
        "project",
        sa.Column("name", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("organisation_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["organisation_id"],
            ["organisation.id"],
            name=op.f("fk_project_organisation_id_organisation"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_project")),
    )
    op.create_table(
        "problem",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("description", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("restricted", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["project_id"], ["project.id"], name=op.f("fk_problem_project_id_project")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_problem")),
    )
    op.create_table(
        "role",
        sa.Column("name", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["project_id"], ["project.id"], name=op.f("fk_role_project_id_project")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_role")),
    )
    op.create_table(
        "invitationkey",
        sa.Column("key", sa.Uuid(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("role_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["role_id"], ["role.id"], name=op.f("fk_invitationkey_role_id_role")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_invitationkey")),
        sa.UniqueConstraint("key", name=op.f("uq_invitationkey_key")),
    )
    op.create_table(
        "submission",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("problem_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column(
            "submitted_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["problem_id"], ["problem.id"], name=op.f("fk_submission_problem_id_problem")
        ),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], name=op.f("fk_submission_user_id_user")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_submission")),
    )
    op.create_table(
        "task",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "type",
            postgresql.ENUM(
                "MULTIPLE_CHOICE",
                "MULTIPLE_RESPONSE",
                "SHORT_ANSWER",
                "PROGRAMMING",
                name="tasktype",
            ),
            nullable=False,
        ),
        sa.Column("autograde", sa.Boolean(), nullable=False),
        sa.Column("other_fields", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("problem_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["problem_id"], ["problem.id"], name=op.f("fk_task_problem_id_problem")
        ),
        sa.PrimaryKeyConstraint("id", "problem_id", name=op.f("pk_task")),
    )
    op.create_table(
        "user_role",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("role_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["role_id"], ["role.id"], name=op.f("fk_user_role_role_id_role")),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], name=op.f("fk_user_role_user_id_user")),
        sa.PrimaryKeyConstraint("user_id", "role_id", name=op.f("pk_user_role")),
    )
    op.create_table(
        "task_attempt",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("task_id", sa.Integer(), nullable=False),
        sa.Column("problem_id", sa.Integer(), nullable=False),
        sa.Column(
            "submitted_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "task_type",
            postgresql.ENUM(
                "MULTIPLE_CHOICE",
                "MULTIPLE_RESPONSE",
                "SHORT_ANSWER",
                "PROGRAMMING",
                name="tasktype",
            ),
            nullable=False,
        ),
        sa.Column("other_fields", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.ForeignKeyConstraint(
            ["task_id", "problem_id"],
            ["task.id", "task.problem_id"],
            name=op.f("fk_task_attempt_task_id_task"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["user.id"], name=op.f("fk_task_attempt_user_id_user")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_task_attempt")),
    )
    op.create_table(
        "submission_attempt",
        sa.Column("submission_id", sa.Integer(), nullable=False),
        sa.Column("task_attempt_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["submission_id"],
            ["submission.id"],
            name=op.f("fk_submission_attempt_submission_id_submission"),
        ),
        sa.ForeignKeyConstraint(
            ["task_attempt_id"],
            ["task_attempt.id"],
            name=op.f("fk_submission_attempt_task_attempt_id_task_attempt"),
        ),
        sa.PrimaryKeyConstraint(
            "submission_id", "task_attempt_id", name=op.f("pk_submission_attempt")
        ),
    )
    op.create_table(
        "task_result",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("task_attempt_id", sa.Integer(), nullable=False),
        sa.Column(
            "task_type",
            postgresql.ENUM(
                "MULTIPLE_CHOICE",
                "MULTIPLE_RESPONSE",
                "SHORT_ANSWER",
                "PROGRAMMING",
                name="tasktype",
            ),
            nullable=False,
        ),
        sa.Column(
            "started_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("completed_at", postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("job_id", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column(
            "status",
            postgresql.ENUM("SUCCESS", "PENDING", "SKIPPED", "FAILED", name="taskevalstatus"),
            nullable=False,
        ),
        sa.Column("result", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.ForeignKeyConstraint(
            ["task_attempt_id"],
            ["task_attempt.id"],
            name=op.f("fk_task_result_task_attempt_id_task_attempt"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_task_result")),
        sa.UniqueConstraint("job_id", name=op.f("uq_task_result_job_id")),
    )
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_table("task_result")
    op.drop_table("submission_attempt")
    op.drop_table("task_attempt")
    op.drop_table("user_role")
    op.drop_table("task")
    op.drop_table("submission")
    op.drop_table("invitationkey")
    op.drop_table("role")
    op.drop_table("problem")
    op.drop_table("project")
    op.drop_table("organisation")
    op.drop_index(op.f("ix_user_username"), table_name="user")
    op.drop_table("user")
    # ### end Alembic commands ###

    # Manually remove ENUM types
    op.execute("DROP TYPE IF EXISTS tasktype")
    op.execute("DROP TYPE IF EXISTS taskevalstatus")
