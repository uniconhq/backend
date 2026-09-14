"""The nine tables Unicon owns.

Everything else a contest is made of lives in Forgejo, Woodpecker or Garage.
All nine are created now, including the ones September does not use, so that
the shape of a table never changes after it holds data.

Enumerations are text with a check constraint rather than a Postgres enum:
adding or renaming a value is one migration that rewrites nothing, where an
enum type needs ALTER TYPE and cannot drop a value at all.

Revision ID: 0001
Revises:
Create Date: 2026-09-12 16:18:02.551286
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "invites",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("scope_kind", sa.Text(), nullable=False),
        sa.Column("scope_id", sa.Text(), nullable=False),
        sa.Column("target_email", sa.Text(), nullable=True),
        sa.Column("target_user_id", sa.BigInteger(), nullable=True),
        sa.Column("grants", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("token_hash", sa.LargeBinary(), nullable=False),
        sa.Column("invited_by_user_id", sa.BigInteger(), nullable=False),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("decided_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("accepted_by_user_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "scope_kind in ('org', 'contest', 'task', 'team')", name=op.f("ck_invites_scope_kind")
        ),
        sa.CheckConstraint(
            "status in ('pending', 'accepted', 'declined', 'revoked', 'expired')",
            name=op.f("ck_invites_status"),
        ),
        sa.CheckConstraint(
            "target_email is not null or target_user_id is not null",
            name=op.f("ck_invites_has_target"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_invites")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_invites_token_hash")),
    )
    op.create_index(
        "ix_invites_scope_kind_scope_id_status",
        "invites",
        ["scope_kind", "scope_id", "status"],
        unique=False,
    )
    op.create_index("ix_invites_target_email", "invites", ["target_email"], unique=False)
    op.create_index("ix_invites_target_user_id", "invites", ["target_user_id"], unique=False)
    op.create_table(
        "judgings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("submission_repo_id", sa.BigInteger(), nullable=False),
        sa.Column("submission_org", sa.Text(), nullable=False),
        sa.Column("submission_repo", sa.Text(), nullable=False),
        sa.Column("submission_tag", sa.Text(), nullable=False),
        sa.Column("submission_commit", sa.Text(), nullable=False),
        sa.Column("submitted_by_user_id", sa.BigInteger(), nullable=True),
        sa.Column("task_repo_id", sa.BigInteger(), nullable=False),
        sa.Column("task_published_tag", sa.Text(), nullable=False),
        sa.Column("task_published_sha", sa.Text(), nullable=False),
        sa.Column("stage", sa.Text(), nullable=False),
        sa.Column("attempt", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column(
            "selected_for_final", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("wait_reason", sa.Text(), nullable=True),
        sa.Column("outcome", sa.Text(), nullable=True),
        sa.Column("verdict", sa.Text(), nullable=True),
        sa.Column("score", sa.Numeric(), nullable=True),
        sa.Column("metrics", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("summary", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("plan_key", sa.Text(), nullable=False),
        sa.Column("bundle_key", sa.Text(), nullable=True),
        sa.Column("result_key", sa.Text(), nullable=True),
        sa.Column("log_key", sa.Text(), nullable=True),
        sa.Column("ci_repo_id", sa.BigInteger(), nullable=True),
        sa.Column("ci_pipeline_number", sa.BigInteger(), nullable=True),
        sa.Column("callback_token_hash", sa.LargeBinary(), nullable=False),
        sa.Column("requested_by_user_id", sa.BigInteger(), nullable=True),
        sa.Column("dispatched_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("started_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("finished_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("deadline_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "outcome is null or outcome in ('verdict', 'contestant_error', 'system_error')",
            name=op.f("ck_judgings_outcome"),
        ),
        sa.CheckConstraint(
            "status in ('queued', 'dispatching', 'dispatched', 'running', 'done', 'failed', 'cancelled')",
            name=op.f("ck_judgings_status"),
        ),
        sa.CheckConstraint(
            "wait_reason is null or wait_reason in ('bundle', 'waiting_for_compute', 'ci_unavailable')",
            name=op.f("ck_judgings_wait_reason"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_judgings")),
        sa.UniqueConstraint(
            "submission_repo_id",
            "submission_tag",
            "stage",
            "attempt",
            name=op.f("uq_judgings_submission_repo_id_submission_tag_stage_attempt"),
        ),
    )
    op.create_index(
        "ix_judgings_status_unfinished",
        "judgings",
        ["status"],
        unique=False,
        postgresql_where=sa.text("status in ('queued', 'dispatching', 'dispatched', 'running')"),
    )
    op.create_index(
        "ix_judgings_submission_repo_id", "judgings", ["submission_repo_id"], unique=False
    )
    op.create_table(
        "jupyter_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("contest_repo_id", sa.BigInteger(), nullable=False),
        sa.Column("task_repo_id", sa.BigInteger(), nullable=False),
        sa.Column("input_id", sa.Text(), nullable=False),
        sa.Column("pool_id", sa.Uuid(), nullable=True),
        sa.Column("server_name", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("spawned_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("last_activity_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("stopped_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("stop_reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status in ('spawning', 'running', 'stopped', 'failed')",
            name=op.f("ck_jupyter_sessions_status"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_jupyter_sessions")),
        sa.UniqueConstraint(
            "user_id",
            "task_repo_id",
            "input_id",
            name=op.f("uq_jupyter_sessions_user_id_task_repo_id_input_id"),
        ),
    )
    op.create_table(
        "participants",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("contest_repo_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("registered_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column(
            "eligibility",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("decided_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("decided_by_user_id", sa.BigInteger(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column(
            "time_extension_seconds", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status in ('pending', 'approved', 'rejected', 'withdrawn', 'removed')",
            name=op.f("ck_participants_status"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_participants")),
        sa.UniqueConstraint(
            "contest_repo_id", "user_id", name=op.f("uq_participants_contest_repo_id_user_id")
        ),
    )
    op.create_index(
        "ix_participants_contest_repo_id_status",
        "participants",
        ["contest_repo_id", "status"],
        unique=False,
    )
    op.create_table(
        "sessions",
        sa.Column("id", sa.LargeBinary(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("username", sa.Text(), nullable=False),
        sa.Column("forge_access_token", sa.LargeBinary(), nullable=False),
        sa.Column("forge_refresh_token", sa.LargeBinary(), nullable=False),
        sa.Column("forge_token_expires_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("ip", postgresql.INET(), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("revoked_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sessions")),
    )
    op.create_index("ix_sessions_expires_at", "sessions", ["expires_at"], unique=False)
    op.create_index("ix_sessions_user_id", "sessions", ["user_id"], unique=False)
    op.create_table(
        "teams",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("contest_repo_id", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column("leader_user_id", sa.BigInteger(), nullable=True),
        sa.Column("created_by_user_id", sa.BigInteger(), nullable=False),
        sa.Column("deleted_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_teams")),
        sa.UniqueConstraint("contest_repo_id", "slug", name=op.f("uq_teams_contest_repo_id_slug")),
    )
    op.create_table(
        "uploads",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("purpose", sa.Text(), nullable=False),
        sa.Column("contest_repo_id", sa.BigInteger(), nullable=True),
        sa.Column("task_repo_id", sa.BigInteger(), nullable=True),
        sa.Column("input_id", sa.Text(), nullable=True),
        sa.Column("object_key", sa.Text(), nullable=False),
        sa.Column("filename", sa.Text(), nullable=False),
        sa.Column("content_type", sa.Text(), nullable=True),
        sa.Column("declared_size", sa.BigInteger(), nullable=False),
        sa.Column("actual_size", sa.BigInteger(), nullable=True),
        sa.Column("sha256", sa.LargeBinary(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("multipart_upload_id", sa.Text(), nullable=True),
        sa.Column("consumed_by", sa.Text(), nullable=True),
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("purpose in ('submission', 'asset')", name=op.f("ck_uploads_purpose")),
        sa.CheckConstraint(
            "status in ('presigned', 'uploaded', 'verified', 'consumed', 'rejected', 'expired')",
            name=op.f("ck_uploads_status"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_uploads")),
        sa.UniqueConstraint("object_key", name=op.f("uq_uploads_object_key")),
    )
    op.create_index("ix_uploads_expires_at", "uploads", ["expires_at"], unique=False)
    op.create_index("ix_uploads_user_id_status", "uploads", ["user_id", "status"], unique=False)
    op.create_table(
        "entrant_repos",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("contest_repo_id", sa.BigInteger(), nullable=False),
        sa.Column("task_repo_id", sa.BigInteger(), nullable=True),
        sa.Column("entrant_kind", sa.Text(), nullable=False),
        sa.Column("entrant_user_id", sa.BigInteger(), nullable=True),
        sa.Column("entrant_team_id", sa.Uuid(), nullable=True),
        sa.Column("forge_repo_name", sa.Text(), nullable=False),
        sa.Column("forge_repo_id", sa.BigInteger(), nullable=True),
        sa.Column("status", sa.Text(), server_default=sa.text("'pending'"), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("ready_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "(entrant_kind = 'team') = (entrant_team_id is not null)",
            name=op.f("ck_entrant_repos_team_entrant_has_team_id"),
        ),
        sa.CheckConstraint(
            "(entrant_kind = 'user') = (entrant_user_id is not null)",
            name=op.f("ck_entrant_repos_user_entrant_has_user_id"),
        ),
        sa.CheckConstraint(
            "entrant_kind in ('user', 'team')", name=op.f("ck_entrant_repos_entrant_kind")
        ),
        sa.CheckConstraint(
            "status in ('pending', 'ready', 'failed')", name=op.f("ck_entrant_repos_status")
        ),
        sa.ForeignKeyConstraint(
            ["entrant_team_id"], ["teams.id"], name=op.f("fk_entrant_repos_entrant_team_id")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_entrant_repos")),
        sa.UniqueConstraint(
            "contest_repo_id",
            "task_repo_id",
            "entrant_user_id",
            "entrant_team_id",
            name="uq_entrant_repos_entrant_and_task",
            postgresql_nulls_not_distinct=True,
        ),
        sa.UniqueConstraint("forge_repo_name", name=op.f("uq_entrant_repos_forge_repo_name")),
    )
    op.create_table(
        "team_members",
        sa.Column("team_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("contest_repo_id", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("requested_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("decided_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("decided_by_user_id", sa.BigInteger(), nullable=True),
        sa.Column("collaborator_synced_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status in ('requested', 'active', 'left', 'removed')",
            name=op.f("ck_team_members_status"),
        ),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"], name=op.f("fk_team_members_team_id")),
        sa.PrimaryKeyConstraint("team_id", "user_id", name=op.f("pk_team_members")),
    )
    op.create_index(
        "uq_team_members_contest_repo_id_user_id_active",
        "team_members",
        ["contest_repo_id", "user_id"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_team_members_contest_repo_id_user_id_active",
        table_name="team_members",
        postgresql_where=sa.text("status = 'active'"),
    )
    op.drop_table("team_members")
    op.drop_table("entrant_repos")
    op.drop_index("ix_uploads_user_id_status", table_name="uploads")
    op.drop_index("ix_uploads_expires_at", table_name="uploads")
    op.drop_table("uploads")
    op.drop_table("teams")
    op.drop_index("ix_sessions_user_id", table_name="sessions")
    op.drop_index("ix_sessions_expires_at", table_name="sessions")
    op.drop_table("sessions")
    op.drop_index("ix_participants_contest_repo_id_status", table_name="participants")
    op.drop_table("participants")
    op.drop_table("jupyter_sessions")
    op.drop_index("ix_judgings_submission_repo_id", table_name="judgings")
    op.drop_index(
        "ix_judgings_status_unfinished",
        table_name="judgings",
        postgresql_where=sa.text("status in ('queued', 'dispatching', 'dispatched', 'running')"),
    )
    op.drop_table("judgings")
    op.drop_index("ix_invites_target_user_id", table_name="invites")
    op.drop_index("ix_invites_target_email", table_name="invites")
    op.drop_index("ix_invites_scope_kind_scope_id_status", table_name="invites")
    op.drop_table("invites")
