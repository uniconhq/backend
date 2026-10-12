"""What the grading routes take and answer with: the sentence a grading is
cancelled with, a grading as an organiser reads it, one among a task's or a
contest's with its task and who submitted it, what a rejudge did, and where
a grading stands after its run reports. Who submitted and a contest's queue
depth go out as the forge's own `Submitter` and `QueueDepth`. A username
the feed is narrowed by keeps the forge's rule for one.
"""

import uuid
from datetime import datetime

from forge.api.gradings import GradingStatus, Submitter
from pydantic import BaseModel

from unicon.schemas.exact import Reported
from unicon.schemas.publications import PublicationNumber
from unicon.schemas.submissions import GradedTest, Outcome

USERNAME_PATTERN = r"^[A-Za-z0-9](?:[-._]?[A-Za-z0-9])*$"
"""Letters, digits, `-`, `_` and `.`, beginning and ending with a letter or
a digit, no two of `-`, `_` and `.` side by side: Forgejo's rule."""
USERNAME_MAX = 40


class GradingProgress(BaseModel):
    """The last progress a grading's run reported: the step it was at and how
    many of that step's containers were done of how many.
    """

    step: str
    done: int
    total: int


class RunResult(BaseModel):
    """What a run's result says of the submission: what stopped the run,
    null when nothing did, a row for every test, the values reported once,
    and, when it stopped on `system_error`, the sentence for staff saying
    why. Where the run put its log stays out.
    """

    stopped: Outcome | None
    tests: list[GradedTest]
    values: Reported
    error: str | None


class CancelRequest(BaseModel):
    """Why staff end the submission, a sentence its contestant reads."""

    reason: str


class Grading(BaseModel):
    """One grading as an organiser managing its task reads it: the
    submission by its number, the publication it grades against, its
    attempt and whether that is the submission's `latest`, the one staff
    cancel or retry, the member who submitted it, `submitted_by`, null when
    a reconcile found it at the forge, where it stands, the reason it failed, the sentence
    staff cancelled it with, its result, whether its log was written, the
    last progress its run reported, its times, and whether the platform made
    it by itself, `automatic`, retrying the attempt before it once that
    failed.

    On a latest attempt that has not finished with a result, still being
    graded, a system error or staff cancelled, `last_good` is the latest
    earlier attempt that did, the one its submission counts meanwhile on
    the boards and to its contestant; null on any other, and when no
    attempt has a result.

    An attempt that is `over_limit` was made to grade a delayed submission
    again and ended at once, run by nothing, since its entrant had no room
    left under the task's most submissions: `limit` is that most, null on
    every other status. On a latest attempt of a submission with no result
    that reads as `system_error` or `over_limit`, `retry_limit` is the
    task's most when a retry now would end over the limit, so the retry's
    confirmation says so before it runs ("Not graded: the entrant has
    reached the limit of 10 submissions for this task."); null otherwise,
    when a retry would grade it.
    """

    id: uuid.UUID
    submission_number: int
    submitted_at: datetime
    publication: PublicationNumber
    attempt: int
    latest: bool
    submitted_by: int | None
    status: GradingStatus
    error: str | None
    cancel_reason: str | None
    result: RunResult | None
    log: bool
    progress: GradingProgress | None
    queued_at: datetime
    dispatched_at: datetime | None
    started_at: datetime | None
    finished_at: datetime | None
    deadline_at: datetime | None
    automatic: bool
    last_good: int | None
    limit: int | None
    retry_limit: int | None


class FeedEntry(BaseModel):
    """One grading among a task's or a contest's: the grading as an
    organiser reads it, its task by name, null for a task the platform has
    no name for, its `label`, the letter of its place in the contest's
    `tasks`, null once the contest no longer lists it or its settings do
    not read, and `by`, whose submission it is: the `entrant` by its id and
    `entrant_name`, the name it is shown under, and the member who
    submitted it by `user_id` and `username`, both null when a reconcile
    found it at the forge, the username null when the forge did not say.
    """

    grading: Grading
    task: str | None
    label: str | None
    by: Submitter


class Rejudged(BaseModel):
    """What a rejudge did: the publication the new attempts grade against,
    how many it queued, how many unfinished attempts against an older
    publication it cancelled first, how many it left to finish against
    the current one, and how many delayed submissions it ended
    `over_limit`, their entrants at the task's most submissions.
    """

    publication: PublicationNumber
    queued: int
    cancelled: int
    left_running: int
    over_limit: int


class CallbackAnswer(BaseModel):
    """Where the grading stands once its run's report is taken."""

    status: GradingStatus
