"""What the grading routes answer with: a grading as an organiser reads it,
what a rejudge did, and where a grading stands after its run reports.
"""

import uuid
from datetime import datetime

from forge.api.gradings import GradingStatus
from pydantic import BaseModel

from unicon.schemas.publications import PublicationNumber
from unicon.schemas.submissions import GradedTest, Outcome


class GradingProgress(BaseModel):
    """The last progress a grading's run reported: the step it was at and how
    many of that step's containers were done of how many.
    """

    step: str
    done: int
    total: int


class Verdict(BaseModel):
    """What a run's verdict says of the submission: its outcome, its named
    numbers, its summary and a row for every test. Where the run put its log
    and the forge's names for what it graded stay out.
    """

    outcome: Outcome
    metrics: dict[str, float]
    summary: str
    tests: list[GradedTest]


class Grading(BaseModel):
    """One grading as an organiser managing its task reads it: the
    submission by its number, the publication it grades against, its stage
    and attempt, where it stands, the reason it failed, its verdict, whether
    its log was written, the last progress its run reported, and its times.
    """

    id: uuid.UUID
    submission_number: int
    submitted_at: datetime
    publication: PublicationNumber
    stage: str
    attempt: int
    status: GradingStatus
    error: str | None
    verdict: Verdict | None
    log: bool
    progress: GradingProgress | None
    queued_at: datetime
    dispatched_at: datetime | None
    started_at: datetime | None
    finished_at: datetime | None
    deadline_at: datetime | None


class Rejudged(BaseModel):
    """What a rejudge did: the publication the new attempts grade against,
    how many it queued, how many unfinished attempts against an older
    publication it cancelled first, how many it left to finish against the
    current one, and how many it passed over because the current
    publication no longer has their stage.
    """

    publication: PublicationNumber
    queued: int
    cancelled: int
    left_running: int
    passed_over: int


class CallbackAnswer(BaseModel):
    """Where the grading stands once its run's report is taken."""

    status: GradingStatus
