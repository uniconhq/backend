"""What the grading routes answer with: a grading as an organiser reads it,
what a rejudge did, and where a grading stands after its run reports.
"""

import uuid
from datetime import datetime
from typing import Any

from forge.api.gradings import GradingRecord, Rejudged
from pydantic import BaseModel

from unicon.schemas.submissions import GradingStatus


class GradingProgress(BaseModel):
    """The last progress a grading's run reported: the step it was at and how
    many of that step's containers were done of how many.
    """

    step: str
    done: int
    total: int


class Grading(BaseModel):
    """One grading as an organiser managing its task reads it: the
    submission by its contestant's workspace and number, the publication it
    grades against, its stage and attempt, where it stands and, while it
    waits, why, the reason it failed, its verdict as the run sent it,
    whether its log was written, the last progress its run reported, how
    often it went back to the queue, and its times.
    """

    id: uuid.UUID
    workspace: str
    submission_number: int
    submitted_at: datetime
    publication: str
    stage: str
    attempt: int
    status: GradingStatus
    wait_reason: str | None
    error: str | None
    verdict: dict[str, Any] | None
    log: bool
    progress: GradingProgress | None
    requeues: int
    queued_at: datetime
    retry_at: datetime | None
    dispatched_at: datetime | None
    started_at: datetime | None
    finished_at: datetime | None
    deadline_at: datetime | None

    @classmethod
    def of(cls, record: GradingRecord) -> Grading:
        return cls(
            id=record.id,
            workspace=str(record.workspace),
            submission_number=record.submission_number,
            submitted_at=record.submitted_at,
            publication=str(record.publication),
            stage=record.stage,
            attempt=record.attempt,
            status=record.status.value,
            wait_reason=record.wait_reason,
            error=record.error,
            verdict=record.verdict,
            log=record.log,
            progress=GradingProgress.model_validate(record.progress)
            if record.progress is not None
            else None,
            requeues=record.requeues,
            queued_at=record.queued_at,
            retry_at=record.retry_at,
            dispatched_at=record.dispatched_at,
            started_at=record.started_at,
            finished_at=record.finished_at,
            deadline_at=record.deadline_at,
        )


class Rejudge(BaseModel):
    """What a rejudge did: the publication the new attempts grade against,
    how many it queued, how many unfinished attempts against an older
    publication it cancelled first, how many it left to finish against the
    current one, and how many it passed over because the current
    publication no longer has their stage.
    """

    publication: str
    queued: int
    cancelled: int
    left_running: int
    passed_over: int

    @classmethod
    def of(cls, rejudged: Rejudged) -> Rejudge:
        return cls(
            publication=str(rejudged.publication),
            queued=rejudged.queued,
            cancelled=rejudged.cancelled,
            left_running=rejudged.left_running,
            passed_over=rejudged.passed_over,
        )


class CallbackAnswer(BaseModel):
    """Where the grading stands once its run's report is taken."""

    status: GradingStatus
