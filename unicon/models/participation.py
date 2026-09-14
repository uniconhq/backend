"""Who takes part: registrations, contest teams and invitations. None of these has
a Forgejo object of its own. A contest team in particular cannot be a Forgejo
team, because org members can list every member and their email.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, Index, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from unicon.db.base import Base
from unicon.domain.identifiers import new_id
from unicon.models.timestamps import TimestampsMixin


class Participant(Base, TimestampsMixin):
    """One row per person per contest, from registration to removal."""

    __tablename__ = "participants"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    contest_repo_id: Mapped[int] = mapped_column(BigInteger)
    user_id: Mapped[int] = mapped_column(BigInteger)
    status: Mapped[str]
    registered_at: Mapped[datetime]
    eligibility: Mapped[dict[str, Any]] = mapped_column(server_default=text("'{}'::jsonb"))

    decided_at: Mapped[datetime | None]
    decided_by_user_id: Mapped[int | None] = mapped_column(BigInteger)
    reason: Mapped[str | None]

    time_extension_seconds: Mapped[int] = mapped_column(server_default=text("0"))

    __table_args__ = (
        CheckConstraint(
            "status in ('pending', 'approved', 'rejected', 'withdrawn', 'removed')",
            name="status",
        ),
        UniqueConstraint("contest_repo_id", "user_id"),
        Index("ix_participants_contest_repo_id_status", "contest_repo_id", "status"),
    )


class Team(Base, TimestampsMixin):
    """A contest team. Not a Forgejo team; see the module docstring."""

    __tablename__ = "teams"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    contest_repo_id: Mapped[int] = mapped_column(BigInteger)
    name: Mapped[str]
    slug: Mapped[str]
    leader_user_id: Mapped[int | None] = mapped_column(BigInteger)
    created_by_user_id: Mapped[int] = mapped_column(BigInteger)
    deleted_at: Mapped[datetime | None]

    __table_args__ = (UniqueConstraint("contest_repo_id", "slug"),)


class TeamMember(Base, TimestampsMixin):
    """Membership of a contest team, including requests that were never accepted."""

    __tablename__ = "team_members"

    team_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("teams.id"), primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    contest_repo_id: Mapped[int] = mapped_column(BigInteger)

    status: Mapped[str]
    requested_at: Mapped[datetime]
    decided_at: Mapped[datetime | None]
    decided_by_user_id: Mapped[int | None] = mapped_column(BigInteger)
    collaborator_synced_at: Mapped[datetime | None]

    __table_args__ = (
        CheckConstraint(
            "status in ('requested', 'active', 'left', 'removed')",
            name="status",
        ),
        Index(
            "uq_team_members_contest_repo_id_user_id_active",
            "contest_repo_id",
            "user_id",
            unique=True,
            postgresql_where=text("status = 'active'"),
        ),
    )


class Invite(Base, TimestampsMixin):
    """An invitation to a scope. May name an email address with no account yet."""

    __tablename__ = "invites"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    scope_kind: Mapped[str]
    scope_id: Mapped[str]

    target_email: Mapped[str | None]

    target_user_id: Mapped[int | None] = mapped_column(BigInteger)
    grants: Mapped[dict[str, Any]]

    token_hash: Mapped[bytes] = mapped_column(unique=True)
    invited_by_user_id: Mapped[int] = mapped_column(BigInteger)
    message: Mapped[str | None]
    expires_at: Mapped[datetime]
    status: Mapped[str]
    decided_at: Mapped[datetime | None]
    accepted_by_user_id: Mapped[int | None] = mapped_column(BigInteger)

    __table_args__ = (
        CheckConstraint("scope_kind in ('org', 'contest', 'task', 'team')", name="scope_kind"),
        CheckConstraint(
            "status in ('pending', 'accepted', 'declined', 'revoked', 'expired')",
            name="status",
        ),
        CheckConstraint(
            "target_email is not null or target_user_id is not null",
            name="has_target",
        ),
        Index("ix_invites_target_email", "target_email"),
        Index("ix_invites_target_user_id", "target_user_id"),
        Index("ix_invites_scope_kind_scope_id_status", "scope_kind", "scope_id", "status"),
    )
