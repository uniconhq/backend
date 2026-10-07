"""What the submission routes take and answer with. A submit names, for each
of the task's contestant inputs, the uploads of its files, or the value of a
text, number, true-or-false or enum input, as the forge's own
`SubmittedInput`. A submission comes back with the latest attempt of its
grading, carrying only what the task's test groups let its contestant see
now: each group by its `show`, `always` with its outcome and its tests,
`verdict` with its outcome and its tests once the task reveals, and
`after_close` with its name and when it is shown. What is not shown is
null. On a task that gives points, a result carries its points, each group
shown its points and most points, and each test row its credit, every one an
exact decimal string.
"""

import uuid
from datetime import datetime
from typing import Any, Literal

from forge.api.submissions import GradingStatus, Show, SubmittedInput
from pydantic import BaseModel, model_validator

from unicon.schemas.exact import Exact, Reported

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
Value = str | int | float | bool
"""A value a contestant gives: text, a number, or true or false."""


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


class Result(BaseModel):
    """The latest attempt of a submission's grading, as its contestant sees
    it: its id, attempt and status, and once it is done, what stopped the
    run, the outcome over the groups shown, each test group as its `show`
    allows and the values reported once. A run that failed on the
    platform's side is `running` to its contestant, with nothing else, until
    staff end it: then it is `cancelled`, with `reason`, the sentence they
    gave, which is null on every other status. Once done on a task that
    gives points, it carries its `points` and the late `factor` they
    include; both are null otherwise.
    """

    id: uuid.UUID
    attempt: int
    status: GradingStatus
    stopped: Outcome | None
    outcome: Outcome | None
    groups: list[GroupShown]
    values: Reported
    reason: str | None
    points: Points | None
    factor: Exact | None


class Submission(BaseModel):
    """One of the caller's submissions of the task: its number among them,
    when it was taken, how many started days after their due it was, and
    its grading.
    """

    number: int
    submitted_at: datetime
    late_days: int
    grading: Result | None


class SubmittedFileInput(BaseModel):
    """What one input of a submission was: the paths of its files in the
    submission, each a download through the download door, or the value
    given. It is read leniently from the submission's `submission.json`: a
    member of the wrong type is left out rather than failing the answer.
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
            "value": value if isinstance(value, Value) else None,
        }


class SubmittedFiles(BaseModel):
    """What a submission was made with, by input id."""

    number: int
    inputs: dict[str, SubmittedFileInput]
