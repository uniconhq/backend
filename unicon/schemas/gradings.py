"""What the grading routes take and answer with: the sentence a grading is
cancelled with, a grading as an organiser reads it, one among a task's or a
contest's with its task and who submitted it, what a rejudge did, a task's
latest regrade of many summed up and what it did to one submission, and
where a grading stands after its run reports. Who submitted and a contest's queue
depth go out as the forge's own `Submitter` and `QueueDepth`. A username
the feed is narrowed by keeps the forge's rule for one.
"""

import uuid
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from forge.api.gradings import GradingStatus, Submitter
from forge.api.regrades import Change, RegradeCause
from pydantic import BaseModel, field_validator

from unicon.schemas.exact import Exact, Reported
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


class RegradeSide(BaseModel):
    """One result a regrade compares, as organisers see it, every group,
    nothing held back, the late factor applied: its attempt, its `points`,
    null on a task that gives no points, how many of its tests were
    `accepted` of how many `tests` it has, the outcome that `stopped` its run
    before its tests, null when nothing did, and each value with a fold and
    a declared direction, folded over every test.
    """

    attempt: int
    points: Exact | None
    accepted: int
    tests: int
    stopped: Outcome | None
    values: dict[str, Exact]


class RegradeChange(BaseModel):
    """What a regrade did to one submission: `change`, and the result it
    replaced, `earlier`, the one that counted when the regrade began, null
    when there was none or it no longer reads, beside its own, `now`, null
    while it has none.

    `up` and `down`: its points went up or down; on a task that gives no
    points, a larger or smaller share of its tests accepted, or with the
    same share, its values with a direction, down when any got worse.
    `stopped`: it now stops before its tests where the earlier result did
    not, which on the classic workflow is "now fails to compile".
    `unchanged`; `new`, graded with no earlier result to compare with;
    `running`, still being graded; `failed`, no result yet, its latest
    attempt a system error or cancelled; `over_limit`, not graded, its
    entrant at the task's most submissions.
    """

    change: Change
    earlier: RegradeSide | None
    now: RegradeSide | None


class RegradeCounts(BaseModel):
    """How many of a regrade's submissions each change counts."""

    up: int
    down: int
    stopped: int
    unchanged: int
    new: int
    running: int
    failed: int
    over_limit: int


class RegradeSummary(BaseModel):
    """A task's latest regrade of many as the contest's page shows it, "Regrade
    of A: 120 graded · 4 went down · 2 now fail to compile · 1 went up": its
    id, the one the feed is read by; its task by name and `label`, the letter
    of its place in the contest's `tasks`, null once the contest no longer
    lists it; what started it, `cause`, a staff `rejudge` or the `save` that
    published `publication`, the publication its attempts grade against;
    when and by whom, by user id and `started_by_name`, their username, null
    when the forge does not say; how many submissions it took, `total`; how
    many it `graded`, finishing with a result (`up`, `down`, `stopped`,
    `unchanged` and `new` together); whether any is still `running`; and
    `counts`, by change. It stays until a newer regrade of the task replaces
    it or a manager of the task dismisses it.
    """

    id: uuid.UUID
    task: str | None
    label: str | None
    cause: RegradeCause
    publication: PublicationNumber
    started_at: datetime
    started_by: int | None
    started_by_name: str | None
    total: int
    graded: int
    running: bool
    counts: RegradeCounts

    @field_validator("counts", mode="before")
    @classmethod
    def _by_name(cls, given: Any) -> Any:
        if isinstance(given, Mapping):
            return {str(change): count for change, count in given.items()}
        return given


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
    when a retry would grade it. `regrade` is the regrade of many the
    attempt belongs to, null for none; `change`, given only on the feed read
    by `regrade`, what that regrade did to the submission.
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
    regrade: uuid.UUID | None
    change: RegradeChange | None


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
    the current one, how many delayed submissions it ended `over_limit`,
    their entrants at the task's most submissions, and `regrade`, the
    regrade of many it is kept as, null when it made no attempt.
    """

    publication: PublicationNumber
    queued: int
    cancelled: int
    left_running: int
    over_limit: int
    regrade: uuid.UUID | None


class CallbackAnswer(BaseModel):
    """Where the grading stands once its run's report is taken."""

    status: GradingStatus
