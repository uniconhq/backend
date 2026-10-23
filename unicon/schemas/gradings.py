"""What the grading routes take and answer with: the sentence a grading is
cancelled with, a mark entered for a submission's value and what was
kept, a task's grading queue, a grading as an organiser reads it, one
among a task's or a contest's with its task and who submitted it, what a
rejudge did, a task's latest regrade of many summed up and what it did to
one submission, a run task's regrade by the values and verdicts it
changed, and where a grading stands after its run reports. Who submitted
and a contest's queue depth go out as the forge's own `Submitter` and
`QueueDepth`. A username the feed is narrowed by keeps the forge's rule
for one.
"""

import uuid
from collections.abc import Mapping
from datetime import datetime
from typing import Any, Literal

from forge.api.gradings import GradingStatus, Submitter
from forge.api.regrades import ChangeKind, RegradeCause
from pydantic import BaseModel, Field, field_validator

from unicon.schemas.exact import Exact, Reported
from unicon.schemas.leaderboards import Counted, Header, LeaderboardRowOwner, SortKey
from unicon.schemas.publications import PublicationNumber
from unicon.schemas.submissions import GradedTest, Outcome, TextRef

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


class RunVerdict(BaseModel):
    """One run of a run task's grading: its id and key as the plan gives
    them, its verdict, 1 `passed` when that is `accepted`, the numbers its
    steps reported, exactly, and the texts, with the label and message
    shown with the verdict, null when no step wrote one.
    """

    id: str
    key: dict[str, Any]
    verdict: Outcome
    passed: int
    reports: dict[str, Exact]
    texts: dict[str, TextRef]
    label: TextRef | None = None
    message: TextRef | None = None


class OnceReports(BaseModel):
    """What the steps done once reported: numbers, exactly, and texts; and
    the outcome each returned, by its id, which the `compiled` fact reads.
    """

    reports: dict[str, Exact]
    texts: dict[str, TextRef]
    outcomes: dict[str, Outcome] = {}


class StaffNote(BaseModel):
    """What a step wrote for staff alone, for one run or, `run` null, once:
    its message to staff and its extras, each null when it wrote none."""

    step: str
    run: str | None
    staff_message: TextRef | None = None
    extras: TextRef | None = None


class RunsResult(BaseModel):
    """A run task's grading's result, version 6, one per pipeline: each run
    it grades with its verdict, what the steps done once reported, what
    staff alone see, and, when a run's verdict is `system_error`, the
    sentence for staff saying why. Where its log went stays out.
    """

    schema_version: Literal[6]
    runs: list[RunVerdict]
    once: OnceReports
    staff: list[StaffNote]
    error: str | None


class CancelRequest(BaseModel):
    """Why staff end the submission, a sentence its contestant reads."""

    reason: str


class EnterMarkRequest(BaseModel):
    """A mark for one of a submission's values that reads an `entered`
    block: the value's name, and the mark written out as a plain decimal,
    such as `7.5`, as text so it stays exact. The forge checks it against
    the bounds the task's live version gives.
    """

    value: str = Field(max_length=64)
    mark: str = Field(max_length=40)


class EnteredMark(BaseModel):
    """A mark as it was kept: the value, the mark as the plain decimal it
    counts as, the user id of who entered it, and when. Every mark entered
    is kept, and the latest is the value's.
    """

    value: str
    mark: str
    by: int
    at: datetime


class CountedBy(BaseModel):
    """A leaderboard's cell that counted a submission: the leaderboard's key and the
    column's name."""

    leaderboard: str
    column: str


class QueuedMark(BaseModel):
    """One of the task's `entered` values and the submission's mark for it,
    null while none is entered."""

    value: str
    mark: Exact | None


class QueuedSubmission(BaseModel):
    """A submission a row's cells counted: its number, each cell that
    counted it, and each of the task's `entered` values with its mark, in
    the task's order.
    """

    number: int
    counted_by: list[CountedBy]
    marks: list[QueuedMark]


class QueueRow(BaseModel):
    """A row in a task's grading queue: whose it is, when the task closed
    for it, its extension included, and the submissions to the task its
    cells counted, oldest first.
    """

    row: LeaderboardRowOwner
    closed_at: datetime
    submissions: list[QueuedSubmission]


class RegradeSide(BaseModel):
    """One result a regrade compares, as organisers see it, every group,
    nothing held back: its attempt, how many of its tests were `accepted` of
    how many `tests` its plan has in its groups, and the outcome that
    `stopped` its run before its tests, null when nothing did.
    """

    attempt: int
    accepted: int
    tests: int
    stopped: Outcome | None


class RegradeChange(BaseModel):
    """What a regrade did to one submission: `change`, and the result it
    replaced, `earlier`, the one that counted when the regrade began, null
    when there was none or it no longer reads, beside its own, `now`, null
    while it has none.

    `up` and `down`: a larger or smaller share of its tests accepted.
    `stopped`: it now stops before its tests where the earlier result did
    not, which on the classic workflow is "now fails to compile".
    `unchanged`; `new`, graded with no earlier result to compare with;
    `running`, still being graded; `failed`, no result yet, its latest
    attempt a system error or cancelled; `over_limit`, not graded, its
    entrant at the task's most submissions.
    """

    change: ChangeKind
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


class ValueChange(BaseModel):
    """One value of a submission a regrade changed: its `name`, its
    number `before` and `after`, exactly, null where it had none or waits,
    and whether it is `waiting` after, for a run or for staff. A value has
    no direction: up and down are a row's place on a leaderboard."""

    name: str
    before: Exact | None
    after: Exact | None
    waiting: bool


class VerdictChange(BaseModel):
    """One run whose verdict a regrade changed, by id, its verdict
    `before` and `after`, null where the grading did not hold the run; or,
    with `run` null, every one of the submission's `runs` runs, each of
    which changed from the same verdict to the same other one."""

    run: str | None
    before: str | None
    after: str | None
    runs: int


class SubmissionChange(BaseModel):
    """One submission a run task's regrade changed: its latest attempt of
    the regrade, `grading`, which the task's gradings read in full, the
    submission by `number`, each value it changed, and the runs whose
    verdict it changed, at most 20 listed and `more_verdicts` counting the
    rest."""

    grading: uuid.UUID
    number: int
    values: list[ValueChange]
    verdicts: list[VerdictChange]
    more_verdicts: int


class CellDiff(BaseModel):
    """One displayed cell of a row, its number before the regrade and
    after, exactly, null where it was or is missing, and the submissions
    the cell after leaves out as still waiting, as the leaderboard does."""

    column: str
    before: Exact | None
    after: Exact | None
    waiting: list[Counted]


class RowDiff(BaseModel):
    """One row of a leaderboard before the regrade and after: whose it is, its
    place on each side, null on a leaderboard with no `sort` or, before, for a
    row that had none, its displayed cells, and its submissions of the
    task the regrade is still grading, whose earlier result the after
    side reads until it ends."""

    row: LeaderboardRowOwner
    place_before: int | None
    place_after: int | None
    cells: list[CellDiff]
    regrading: list[Counted]


class LeaderboardDiff(BaseModel):
    """One leaderboard that reads the regraded task, directly or through another
    leaderboard's column, as staff read it, every row and cell and no hold: its
    key and title, its displayed columns' headers as they stand after, the
    columns it sorts by, and each row in its order after the regrade;
    `unread` with no rows when the publication the results counted under
    before no longer reads, so there is nothing to compare."""

    leaderboard: str
    title: str
    headers: list[Header]
    sort: list[SortKey]
    rows: list[RowDiff]
    unread: bool


class RunRegradeSummary(BaseModel):
    """A run task's regrade by what it changed: its `id`, what started it,
    the publication it grades against, how many submissions it took,
    `total`, how many are still `running`, how many ended with no
    result, `failed`, and how many it cannot compare, `unread`, since
    the publication their result counted under no longer reads;
    `changed`, each submission whose values or verdicts it changed, old
    to new, in the order they were made, at most 100, with `more_changed`
    counting the rest, an attempt compared with the one that counted when
    the regrade began, both worked out as organisers read them, the
    extensions and marks as they stand now; and `leaderboards`, each leaderboard that reads the
    task before and after, given to a manager or admin of the contest
    alone, null for anyone else.
    """

    id: uuid.UUID
    cause: RegradeCause
    publication: PublicationNumber
    total: int
    running: int
    failed: int
    unread: int
    changed: list[SubmissionChange]
    more_changed: int
    leaderboards: list[LeaderboardDiff] | None


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
    the leaderboards and to its contestant; null on any other, and when no
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

    A run task's submission is graded by up to two pipelines, each with
    attempts of its own: `early`, the runs shown during the contest, and
    `late`, the rest, made once the early one is done, with `early` naming
    the early attempt it follows, null on an early one. Its `result` is a
    `RunsResult`; a task with tests has `early` attempts alone, each with a
    `RunResult`.
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
    result: RunResult | RunsResult | None
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
    pipeline: Literal["early", "late"]
    early: uuid.UUID | None


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
