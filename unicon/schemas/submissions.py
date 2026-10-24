"""What the submission routes take and answer with. A submit names, for each of
the task's contestant inputs, the uploads of its files, or the value of a
text, number, true-or-false or enum input, or, for an input given once per
tuple, its parts, each the same, as the forge's own `SubmittedInput`: a
number as the text of its plain decimal digits, `2.5`, the form every number
is served in, never a JSON number. A submission comes back with the latest
attempt of its grading, carrying only what the task's `show` lets its
contestant see now. What is not shown is null.
"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from forge.api.submissions import GradingStatus, SubmissionState, SubmittedInput
from pydantic import BaseModel, field_validator, model_validator

from unicon.schemas.exact import Exact, exactly

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
"""The runner's list of outcomes, which each run's verdict and each step done
once take one of. Forge keeps a result only once it matches the runner's
schema, so every outcome read back is on it."""
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

    @field_validator("inputs", mode="before")
    @classmethod
    def _no_json_numbers(cls, given: Any) -> Any:
        """A value is text, true or false: a JSON number would otherwise be
        read as true or false (`1`, `0`, `1.0`), and a number is sent as the
        text of its digits (#427). A part's value is held to the same.
        """
        if isinstance(given, dict):
            for name, entry in given.items():
                parts = entry.get("parts") if isinstance(entry, dict) else None
                for part in [entry, *(parts.values() if isinstance(parts, dict) else [])]:
                    value = part.get("value") if isinstance(part, dict) else None
                    if isinstance(value, int | float) and not isinstance(value, bool):
                        raise ValueError(
                            f'The value for {name} must be sent as text, such as "2.5".'
                        )
        return given


class TextRef(BaseModel):
    """A text a step wrote, read apart and only while the result shows it.
    Organisers are told the stored output that holds it and that output's
    name, and read it by them. An entrant is told neither, both null, since
    the output may be another entrant's and its id says when it was made:
    they read it by where it is shown, its run's group and place, or the
    steps done once, and the text's name or `label` or `message`.
    """

    output: str | None = None
    name: str | None = None


class RunShown(BaseModel):
    """One run of a grading as its entrant sees it: the group
    `show` lists that shows it, its place in that group from 1 ("Test 3"),
    its key as the plan gives it, leaving out a file not yet shown, its
    verdict, `passed`, 1 when that is `accepted`, the numbers its steps
    reported, exactly, and its texts, with the `label` and `message` shown
    with its verdict, null when no step wrote one. A run in two groups
    shown is shown in each; a run no group shown holds is never shown, even
    when a value shown reads it. Organisers read every run, under `all` in
    the task's order, with its `id`, which counts every run of the task;
    `id` is null for an entrant. A run a row holds that the task's latest
    publication no longer has is `dropped`, listed to organisers after the
    rest; never to an entrant.
    """

    group: str
    place: int
    id: str | None = None
    dropped: bool = False
    key: dict[str, Any]
    verdict: Outcome
    passed: int
    reports: dict[str, Exact]
    texts: dict[str, TextRef] = {}
    label: TextRef | None = None
    message: TextRef | None = None
    titles: list[str | None] | None = None


class RunValue(BaseModel):
    """One value of a task's scoring as its reader sees it: its name,
    its `number`, exact, null when it is missing, waiting or text; its
    `text`, null when it is a number, missing or waiting; whether
    it is `waiting` for staff, which an entrant reads as "being checked",
    told only once the runs it waits on are early or shown; and whether it
    is `self_reported`, reading a column the entrant could set. Organisers
    also read the time `show` lists it under, null when never, and what it
    read: `runs` by id, `values` and `facts`; each is null for an entrant.
    """

    name: str
    number: Exact | None
    text: str | None = None
    waiting: bool
    self_reported: bool
    show: Literal["now", "after_close", "on_release"] | None = None
    runs: list[str] | None = None
    values: list[str] | None = None
    facts: list[str] | None = None


class OnceShown(BaseModel):
    """What a grading's steps done once reported, as its reader is shown
    it: numbers, exactly, and texts, the compile log among them; for an
    entrant, only the reports `show` lists, by name."""

    reports: dict[str, Exact] = {}
    texts: dict[str, TextRef] = {}


class Scored(BaseModel):
    """What a result holds beside where it stands, as `Result` and
    `OrganisedResult` say.
    """

    id: uuid.UUID
    attempt: int
    reason: str | None
    limit: int | None
    runs: list[RunShown] = []
    run_values: list[RunValue] = []
    once: OnceShown = OnceShown()
    compiled: int | None = None


class Result(Scored):
    """The attempt of a submission's grading that counts, as its contestant
    sees it: the latest that finished with a result, as the leaderboards
    count it, so a regrade under way, a failure or a cancel leaves the
    result as it was, and while none has, the latest. Its id, attempt and
    status, in the contestant's words: `queued` until its run is started,
    `grading` while it is graded, `graded` once it has a result, `delayed`
    while it has none and its grading failed on the platform's side,
    `over_limit` once it was to be graded again with no room left under the
    task's most submissions, and `cancelled` once staff end it; organisers
    read the grading's own status in the gradings routes. A `delayed` one
    carries nothing else: it is tried again once by itself, and then waits
    for staff, who grade it again or end it: then it is `cancelled`, with
    `reason`, the sentence they gave, which is null on every other status. A
    delayed one is graded again only while its
    entrant's submissions with a result, those waiting that are not
    delayed, and the delayed ones made before it are fewer than the task's
    most, so the first ones to get a result count, and otherwise it is
    `over_limit`, with `limit`,
    the most it reached ("Not graded: you had reached the limit of 10
    submissions for this task."), and nothing else; `limit` is null on every
    other status.

    `run_values` holds each value of its scoring its entrant is shown,
    worked out on every read, and `runs` the runs, those listed under `now` from the start,
    those under `after_close` once the task reveals, and those under
    `on_release` while staff have released the task's results, hidden
    again when they take the release back. `once` holds what its steps
    done once reported that `show` lists, the compile log among them when
    listed, once a run is shown; and `compiled` 1, or 0 when a compile
    done once stopped it, from the time `show` lists it or once a run is
    shown, null while its compile is still to run. A task with
    nothing shown during the contest is `submitted` until the reveal, which
    a page words "Submitted, results after the contest". After the reveal,
    while its late runs are still being graded, it is `grading` or
    `delayed`. A grading whose runs failed for the platform is `delayed`
    with the runs it gave, a value reading one of its failed early runs
    `waiting`. `reveal_at` is when the task reveals, until then, as what its
    entrant reads changes then with no grading's change to say so, so a page
    open on it reads it again then; null once it has revealed.
    """

    status: SubmissionState
    reveal_at: datetime | None = None


class OrganisedResult(Scored):
    """A submission's grading as organisers read it beside the grading
    itself: the payload its contestant reads, with everything filled in as
    once the task has revealed. `status` is the grading's own, as in the
    gradings routes. Every value and run is there at once, each value with
    when it shows and what it read, and `facts` holds `seconds_late`,
    `seconds` and `compiled` as the values read them.
    """

    status: GradingStatus
    facts: dict[str, Exact] = {}


class Numbered(BaseModel):
    """A submission's number among its row's and when it was taken."""

    number: int
    submitted_at: datetime


class Submission(Numbered):
    """One of the caller's submissions of the task: its number among them,
    when it was taken, and its grading.
    """

    grading: Result | None


class OrganisedSubmission(Numbered):
    """One submission of an entrant, as organisers read it: its number
    among the entrant's, when it was taken, and its grading with everything
    filled in.
    """

    grading: OrganisedResult | None


class SubmittedPart(BaseModel):
    """What one part of an input given in parts was: the paths of its files
    in the submission, each a download through the download door, or the
    value given, a number as its exact decimal digits. It is read leniently
    from the submission's `submission.json`: a member of the wrong type is
    left out rather than failing the answer.
    """

    files: list[str]
    value: Value | None

    @model_validator(mode="before")
    @classmethod
    def _leniently(cls, given: Any) -> dict[str, Any]:
        return _files_and_value(given if isinstance(given, dict) else {})


class SubmittedFileInput(SubmittedPart):
    """What one input of a submission was: the paths of its files in the
    submission, each a download through the download door, or the value
    given, a number as its exact decimal digits; or, for an input given
    once per tuple, its `parts` by number from "1", only the parts given,
    its own `files` empty and `value` null, and `parts` null on any other.
    It is read leniently from the submission's `submission.json`: a member
    of the wrong type is left out rather than failing the answer.
    """

    parts: dict[str, SubmittedPart] | None

    @model_validator(mode="before")
    @classmethod
    def _leniently(cls, given: Any) -> dict[str, Any]:
        found = given if isinstance(given, dict) else {}
        parts = found.get("parts")
        return {
            **_files_and_value(found),
            "parts": {
                number: part
                for number, part in parts.items()
                if isinstance(number, str) and isinstance(part, dict)
            }
            if isinstance(parts, dict)
            else None,
        }


class SubmittedFiles(BaseModel):
    """What a submission was made with, by input id."""

    number: int
    inputs: dict[str, SubmittedFileInput]


def _files_and_value(found: dict[str, Any]) -> dict[str, Any]:
    """The `files` and `value` of an input or a part as `submission.json`
    holds them, each member of the wrong type left out.
    """
    files = found.get("files")
    value = found.get("value")
    return {
        "files": [path for path in files if isinstance(path, str)]
        if isinstance(files, list)
        else [],
        "value": value if isinstance(value, Value) else _digits(value),
    }


def _digits(value: object) -> str | None:
    """A number read from `submission.json` as its exact decimal digits, or
    none for anything that is not one.
    """
    if isinstance(value, bool) or not isinstance(value, int | float | Decimal):
        return None
    digits = exactly(value)
    return digits if isinstance(digits, str) else None
