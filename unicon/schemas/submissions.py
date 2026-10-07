"""What the submission routes take and answer with. A submit names, for each
of the task's contestant inputs, the uploads of its files, or the value of a
text, number, true-or-false or enum input, as the forge's own
`SubmittedInput`. A submission comes back with the latest attempt of its
grading, carrying only what the task's test groups let its contestant see
now: each group by its `show`, `always` with its outcome and its tests,
`verdict` with its outcome and its tests once the task reveals, and
`after_close` with its name and when it is shown. What is not shown is
null.
"""

import uuid
from datetime import datetime
from typing import Any, Literal

from forge.api.submissions import GradingStatus, Show, SubmittedInput
from pydantic import BaseModel, model_validator

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
Reported = int | float | str
"""A value a run reported: a number, or text of at most 10,000 characters."""


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
    and the values its steps reported for it.
    """

    test: str
    outcome: Outcome
    values: dict[str, Reported]


class GroupShown(BaseModel):
    """One test group as the contestant sees it now: its name, its `show`,
    its outcome once its verdict is shown, its tests once they are, when
    what is held back is shown, null once nothing is, and whether it ran on
    this grading. A group that did not run has no outcome, no tests and
    nothing held back.
    """

    group: str
    show: Show
    outcome: Outcome | None
    tests: list[GradedTest] | None
    shown_at: datetime | None
    ran: bool


class Result(BaseModel):
    """The latest attempt of a submission's grading, as its contestant sees
    it: its id, attempt and status, and once it is done, what stopped the
    run, the outcome over the groups shown, each test group as its `show`
    allows and the values reported once. A run that failed on the
    platform's side is `running` to its contestant, with nothing else, until
    staff end it: then it is `cancelled`, with `reason`, the sentence they
    gave, which is null on every other status.
    """

    id: uuid.UUID
    attempt: int
    status: GradingStatus
    stopped: Outcome | None
    outcome: Outcome | None
    groups: list[GroupShown]
    values: dict[str, Reported]
    reason: str | None


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
