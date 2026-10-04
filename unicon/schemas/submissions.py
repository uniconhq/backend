"""What the submission routes take and answer with. A submit names, for each
of the task's contestant inputs, the uploads of its files and the language
of a code input, or the value of a text, number or true-or-false input, as
the forge's own `SubmittedInput`. A submission comes back with the latest
attempt of its grading at each of the task's stages, carrying only what that
stage's `show` lets its contestant see: `full` the outcome, the metrics, the
summary, the row of every test and whether there is a log; `metrics` the
outcome and the metrics; `hidden` the status alone. What is not shown is
null.
"""

import uuid
from datetime import datetime
from typing import Any, Literal

from forge.api.submissions import GradingStatus, Show, SubmittedInput
from pydantic import BaseModel, model_validator

Outcome = Literal[
    "accepted",
    "partial",
    "wrong_answer",
    "time_limit",
    "memory_limit",
    "output_limit",
    "runtime_error",
    "compile_error",
    "skipped",
    "system_error",
]
"""The runner's list of outcomes, which a run and each of its tests take one
of. Forge keeps a verdict only once it matches the runner's schema, so every
outcome read back is on it."""
Value = str | int | float | bool


class SubmitRequest(BaseModel):
    """A submit: `idempotency_key` is 8 to 128 letters, digits, `-` and `_`,
    made once by the browser for this submit, so sending it again answers
    with the submission it made and makes nothing. `inputs` is keyed by the
    id of each of the task's contestant inputs, and forge checks them
    against the task's inputs.
    """

    idempotency_key: str
    inputs: dict[str, SubmittedInput]


class GradedTest(BaseModel):
    """One test's row of a verdict: its name as the task spells it, its own
    outcome, its time in milliseconds and peak memory in KiB, each null when
    the step was not measured, its named numbers, and the checker's note
    when there is one.
    """

    id: str
    outcome: Outcome
    time_ms: int | None
    memory_kb: int | None
    metrics: dict[str, float]
    message: str | None = None


class Result(BaseModel):
    """One grading of a submission at one stage, as its contestant sees it:
    its id, stage, attempt and status, the stage's `show`, and of its
    verdict what that allows: the `outcome`, the named `metrics`, the
    `summary` and a row for every test. `log` says whether its run log can
    be read.
    """

    id: uuid.UUID
    stage: str
    attempt: int
    status: GradingStatus
    show: Show
    outcome: Outcome | None
    metrics: dict[str, float] | None
    summary: str | None
    tests: list[GradedTest] | None
    log: bool


class Submission(BaseModel):
    """One of the caller's submissions of the task: its number among them,
    when it was taken, and its grading at each stage in the order the task
    lists its stages.
    """

    number: int
    submitted_at: datetime
    gradings: list[Result]


class SubmittedFileInput(BaseModel):
    """What one input of a submission was: the paths of its files in the
    submission, each a download through the download door, and the language of a code
    input; or the value given. It is read leniently from the submission's
    `submission.json`: a member of the wrong type is left out rather than
    failing the answer.
    """

    files: list[str]
    language: str | None
    value: Value | None

    @model_validator(mode="before")
    @classmethod
    def _leniently(cls, given: Any) -> dict[str, Any]:
        found = given if isinstance(given, dict) else {}
        files = found.get("files")
        language = found.get("language")
        value = found.get("value")
        return {
            "files": [path for path in files if isinstance(path, str)]
            if isinstance(files, list)
            else [],
            "language": language if isinstance(language, str) else None,
            "value": value if isinstance(value, Value) else None,
        }


class SubmittedFiles(BaseModel):
    """What a submission was made with, by input id."""

    number: int
    inputs: dict[str, SubmittedFileInput]
