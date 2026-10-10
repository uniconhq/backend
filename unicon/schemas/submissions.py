"""What the submission routes take and answer with. A submit names, for each
of the task's contestant inputs, the uploads of its files, or the value of a
text, number, true-or-false or enum input, as the forge's own
`SubmittedInput`: a number as the text of its plain decimal digits, `2.5`,
the form every number is served in, never a JSON number. A submission
comes back with the latest attempt of its grading, carrying only what the
task's test groups let its contestant see now: each group by its `show`,
`always` with its outcome and its tests, `verdict` with its outcome and its
tests once the task reveals, and `after_close` with its name and when it is
shown. What is not shown is null. On a task that gives points, a result
carries its points, each group shown its points and most points, and each
test row its credit, every one an exact decimal string.
"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from forge.api.submissions import GradingStatus, Show, SubmissionState, SubmittedInput
from pydantic import BaseModel, model_validator

from unicon.schemas.exact import Exact, Reported, exactly

Outcome = Literal[
    "accepted",
    "wrong_answer",
    "time_limit",
    "memory_limit",
    "output_limit",
    "runtime_error",
    "compile_error",
    "skipped",
    "system_error",
]
"""The runner's list of outcomes, which each test and what stopped a run
take one of. Forge keeps a result only once it matches the runner's schema,
so every outcome read back is on it."""
Value = str | bool
"""A value a contestant gives: text, a number as its exact decimal digits, or
true or false. A number travels as its digits both ways, so one of 30
significant digits is never read into a float."""


class SubmitRequest(BaseModel):
    """A submit: `idempotency_key` is 8 to 128 letters, digits, `-` and `_`,
    made once by the browser for this submit, so sending it again answers
    with the submission it made and makes nothing. `inputs` is keyed by the
    id of each of the task's contestant inputs, and forge checks them
    against the task's inputs; a value left out takes its default.
    """

    idempotency_key: str
    inputs: dict[str, SubmittedInput]


class GradedTest(BaseModel):
    """One test's row of a result: its id, `<group>/<test>`, its outcome,
    and the values its steps reported for it. Scored, it carries its credit,
    from 0 to 1, and, on a relative credit, the best value that credit is
    measured against; both are null otherwise.
    """

    test: str
    outcome: Outcome
    values: Reported
    credit: Exact | None = None
    best: Exact | None = None


class GroupShown(BaseModel):
    """One test group as the contestant sees it now: its name, its `show`,
    its outcome once its verdict is shown, its tests once they are, when
    what is held back is shown, null once nothing is, and whether it ran on
    this grading. A group that did not run has no outcome, no tests and
    nothing held back. On a task that gives points, `max` is the most the
    group gives and `points` what it gave, once its verdict is shown.
    """

    group: str
    show: Show
    outcome: Outcome | None
    tests: list[GradedTest] | None
    shown_at: datetime | None
    ran: bool
    points: Exact | None
    max: Exact | None


class Points(BaseModel):
    """A submission's points as its contestant sees them: those shown, those
    still pending on groups whose verdict is not shown yet, and when they
    are shown, null when none are pending.
    """

    shown: Exact
    pending: Exact
    pending_until: datetime | None


class Scored(BaseModel):
    """What a result holds beside where it stands, as `Result` and
    `OrganisedResult` say.
    """

    id: uuid.UUID
    attempt: int
    stopped: Outcome | None
    outcome: Outcome | None
    groups: list[GroupShown]
    values: Reported
    folded: dict[str, Exact]
    reason: str | None
    points: Points | None
    factor: Exact | None


class Result(Scored):
    """The latest attempt of a submission's grading, as its contestant sees
    it: its id, attempt and status, and once it is done, what stopped the
    run, the outcome over the groups shown, each test group as its `show`
    allows, the values reported once, and `folded`, each per-test value
    with a fold, folded over the tests shown, a test without it counting as
    its worst bound. `status` is in the contestant's words: `queued` until
    its run is started, `grading` while it is graded, `graded` once it has
    a result, `cancelled` once staff end it; organisers read the grading's
    own status in the gradings routes. A run that failed on the platform's
    side is `grading` to its contestant, with nothing else, until staff end
    it: then it is `cancelled`, with `reason`, the sentence they gave, which
    is null on every other status. Once done on a task that gives points, it carries
    its `points` and the late `factor` they include; both are null
    otherwise. While a sealed step's stop is held to the reveal, nothing of
    the run is shown: every group reads as hidden.
    """

    status: SubmissionState


class OrganisedResult(Scored):
    """A submission's grading as organisers read it beside the grading
    itself: the payload its contestant reads, with everything filled in as
    once the task has revealed, so every group's outcome, tests and points
    and every value a sealed step reported are there, its points all shown
    and none pending. Each group's `shown_at` is kept as a note of when its
    contestant is shown it, null once they see its tests. `status` is the
    grading's own, as in the gradings routes.
    """

    status: GradingStatus


class Numbered(BaseModel):
    """A submission's number among its row's, when it was taken, and how
    many started days after the row's due it was.
    """

    number: int
    submitted_at: datetime
    late_days: int


class Submission(Numbered):
    """One of the caller's submissions of the task: its number among them,
    when it was taken, how many started days after their due it was, and
    its grading.
    """

    grading: Result | None


class OrganisedSubmission(Numbered):
    """One submission of a contestant or a team, as organisers read it:
    its number among the row's, when it was taken, how many started days
    late, and its grading with everything filled in.
    """

    grading: OrganisedResult | None


class SubmittedFileInput(BaseModel):
    """What one input of a submission was: the paths of its files in the
    submission, each a download through the download door, or the value
    given, a number as its exact decimal digits. It is read leniently from
    the submission's `submission.json`: a member of the wrong type is left
    out rather than failing the answer.
    """

    files: list[str]
    value: Value | None

    @model_validator(mode="before")
    @classmethod
    def _leniently(cls, given: Any) -> dict[str, Any]:
        found = given if isinstance(given, dict) else {}
        files = found.get("files")
        value = found.get("value")
        return {
            "files": [path for path in files if isinstance(path, str)]
            if isinstance(files, list)
            else [],
            "value": value if isinstance(value, Value) else _digits(value),
        }


class SubmittedFiles(BaseModel):
    """What a submission was made with, by input id."""

    number: int
    inputs: dict[str, SubmittedFileInput]


def _digits(value: object) -> str | None:
    """A number read from `submission.json` as its exact decimal digits, or
    none for anything that is not one.
    """
    if isinstance(value, bool) or not isinstance(value, int | float | Decimal):
        return None
    digits = exactly(value)
    return digits if isinstance(digits, str) else None
