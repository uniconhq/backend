"""Notebook servers spawned for a contestant working in the browser. JupyterHub
knows a server is running; it does not know which task input it was spawned
for.
"""

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from unicon.db.base import Base
from unicon.domain.identifiers import new_id
from unicon.models.timestamps import TimestampsMixin


class JupyterSession(Base, TimestampsMixin):
    __tablename__ = "jupyter_sessions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    user_id: Mapped[int] = mapped_column(BigInteger)
    contest_repo_id: Mapped[int] = mapped_column(BigInteger)
    task_repo_id: Mapped[int] = mapped_column(BigInteger)
    input_id: Mapped[str]

    pool_id: Mapped[uuid.UUID | None]

    server_name: Mapped[str]
    status: Mapped[str]
    spawned_at: Mapped[datetime]
    last_activity_at: Mapped[datetime | None]
    stopped_at: Mapped[datetime | None]
    stop_reason: Mapped[str | None]

    __table_args__ = (
        CheckConstraint(
            "status in ('spawning', 'running', 'stopped', 'failed')",
            name="status",
        ),
        UniqueConstraint("user_id", "task_repo_id", "input_id"),
    )
