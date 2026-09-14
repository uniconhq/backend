"""One grading run of one submission, at one stage, on one attempt. The full
verdict lives in Garage; this row points at it and keeps the copy Unicon reads,
plus what the pipeline does not know.
"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import BigInteger, CheckConstraint, Index, Numeric, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from unicon.db.base import Base
from unicon.domain.identifiers import new_id
from unicon.models.timestamps import TimestampsMixin


class Judging(Base, TimestampsMixin):
    __tablename__ = "judgings"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)

    submission_repo_id: Mapped[int] = mapped_column(BigInteger)
    submission_org: Mapped[str]
    submission_repo: Mapped[str]
    submission_tag: Mapped[str]
    submission_commit: Mapped[str]
    submitted_by_user_id: Mapped[int | None] = mapped_column(BigInteger)

    task_repo_id: Mapped[int] = mapped_column(BigInteger)
    task_published_tag: Mapped[str]
    task_published_sha: Mapped[str]
    stage: Mapped[str]

    attempt: Mapped[int] = mapped_column(server_default=text("1"))
    selected_for_final: Mapped[bool] = mapped_column(server_default=text("false"))

    status: Mapped[str]
    wait_reason: Mapped[str | None]
    outcome: Mapped[str | None]
    verdict: Mapped[str | None]

    score: Mapped[Decimal | None] = mapped_column(Numeric)
    metrics: Mapped[dict[str, Any] | None]
    summary: Mapped[dict[str, Any] | None]

    plan_key: Mapped[str]
    bundle_key: Mapped[str | None]
    result_key: Mapped[str | None]

    log_key: Mapped[str | None]

    ci_repo_id: Mapped[int | None] = mapped_column(BigInteger)

    ci_pipeline_number: Mapped[int | None] = mapped_column(BigInteger)
    callback_token_hash: Mapped[bytes]

    requested_by_user_id: Mapped[int | None] = mapped_column(BigInteger)

    dispatched_at: Mapped[datetime | None]
    started_at: Mapped[datetime | None]
    finished_at: Mapped[datetime | None]
    deadline_at: Mapped[datetime | None]
    error_message: Mapped[str | None]

    __table_args__ = (
        CheckConstraint(
            "status in ('queued', 'dispatching', 'dispatched', 'running', "
            "'done', 'failed', 'cancelled')",
            name="status",
        ),
        CheckConstraint(
            "wait_reason is null or wait_reason in "
            "('bundle', 'waiting_for_compute', 'ci_unavailable')",
            name="wait_reason",
        ),
        CheckConstraint(
            "outcome is null or outcome in ('verdict', 'contestant_error', 'system_error')",
            name="outcome",
        ),
        UniqueConstraint("submission_repo_id", "submission_tag", "stage", "attempt"),
        Index("ix_judgings_submission_repo_id", "submission_repo_id"),
        Index(
            "ix_judgings_status_unfinished",
            "status",
            postgresql_where=text("status in ('queued', 'dispatching', 'dispatched', 'running')"),
        ),
    )
