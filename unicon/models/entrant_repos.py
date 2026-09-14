"""Provisioning state of the repos an entrant works in: a desk repo for the
contest and one submission repo per task. Forgejo only knows whether a repo
exists, so pending and failed have nowhere else to live.
"""

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from unicon.db.base import Base
from unicon.domain.identifiers import new_id
from unicon.models.timestamps import TimestampsMixin


class EntrantRepo(Base, TimestampsMixin):
    __tablename__ = "entrant_repos"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    contest_repo_id: Mapped[int] = mapped_column(BigInteger)
    task_repo_id: Mapped[int | None] = mapped_column(BigInteger)

    entrant_kind: Mapped[str]
    entrant_user_id: Mapped[int | None] = mapped_column(BigInteger)
    entrant_team_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("teams.id"))

    forge_repo_name: Mapped[str] = mapped_column(unique=True)

    forge_repo_id: Mapped[int | None] = mapped_column(BigInteger)
    status: Mapped[str] = mapped_column(server_default=text("'pending'"))
    last_error: Mapped[str | None]
    ready_at: Mapped[datetime | None]

    __table_args__ = (
        CheckConstraint("entrant_kind in ('user', 'team')", name="entrant_kind"),
        CheckConstraint(
            "(entrant_kind = 'user') = (entrant_user_id is not null)",
            name="user_entrant_has_user_id",
        ),
        CheckConstraint(
            "(entrant_kind = 'team') = (entrant_team_id is not null)",
            name="team_entrant_has_team_id",
        ),
        CheckConstraint("status in ('pending', 'ready', 'failed')", name="status"),
        UniqueConstraint(
            "contest_repo_id",
            "task_repo_id",
            "entrant_user_id",
            "entrant_team_id",
            name="uq_entrant_repos_entrant_and_task",
            postgresql_nulls_not_distinct=True,
        ),
    )
