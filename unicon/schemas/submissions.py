"""What the submission routes take and answer with. A submit names, for each
of the task's contestant inputs, the uploads of its files, or the value of a
text, number, true-or-false or enum input, as the forge's own
`SubmittedInput`: a number as the text of its plain decimal digits, `2.5`,
the form every number is served in, never a JSON number. A submission
comes back with the latest attempt of its grading, carrying only what the
task's test groups let its contestant see now: each group by its `show`,
`always` with its outcome and its tests, `verdict` with its outcome and its
tests once the task reveals, and `after_close` with its name and when it is
shown. What is not shown is null.
"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from forge.api.submissions import GradingStatus, Show, SubmissionState, SubmittedInput
from pydantic import BaseModel, field_validator, model_validator

from unicon.schemas.exact import Exact, Reported, exactly
from unicon.schemas.publications import ValueMeaning

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

    @field_validator("inputs", mode="before")
    @classmethod
    def _no_json_numbers(cls, given: Any) -> Any:
        """A value is text, true or false: a JSON number would otherwise be
        read as true or false (`1`, `0`, `1.0`), and a number is sent as the
        text of its digits (#427).
        """
        if isinstance(given, dict):
            for name, entry in given.items():
                value = entry.get("value") if isinstance(entry, dict) else None
                if isinstance(value, int | float) and not isinstance(value, bool):
                    raise ValueError(f'The value for {name} must be sent as text, such as "2.5".')
        return given


class GradedTest(BaseModel):
    """One test's row of a result: its id, `<group>/<test>`, its outcome,
    and the values its steps reported for it.
    """

    test: str
    outcome: Outcome
    values: Reported


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
    """One run of a run task's grading as its entrant sees it: the group
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
    """One value of a run task's scoring as its reader sees it: its name,
    its `number`, exact, null when it is missing or waiting; whether
    it is `waiting` for staff, which an entrant reads as "being checked",
    told only once the runs it waits on are early or shown; and whether it
    is `self_reported`, reading a column the entrant could set. Organisers
    also read the time `show` lists it under, null when never, and what it
    read: `runs` by id, `values` and `facts`; each is null for an entrant.
    """

    name: str
    number: Exact | None
    waiting: bool
    self_reported: bool
    show: Literal["now", "after_close", "on_release"] | None = None
    runs: list[str] | None = None
    values: list[str] | None = None
    facts: list[str] | None = None


class OnceShown(BaseModel):
    """What a run task's steps done once reported, as its reader is shown
    it: numbers, exactly, and texts, the compile log among them; for an
    entrant, only the reports `show` lists, by name."""

    reports: dict[str, Exact] = {}
    texts: dict[str, TextRef] = {}


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
    reason: str | None
    limit: int | None
    meanings: list[ValueMeaning]
    runs: list[RunShown] = []
    run_values: list[RunValue] = []
    once: OnceShown = OnceShown()
    compiled: int | None = None


class Result(Scored):
    """The attempt of a submission's grading that counts, as its contestant
    sees it: the latest that finished with a result, as the leaderboards count
    it, so a regrade under way, a failure or a cancel leaves the result as
    it was, and while none has, the latest. Its id, attempt and status, and
    once it is done, what stopped the
    run, the outcome over the groups shown, each test group as its `show`
    allows, the values reported once, each test's row with what it
    reported, and `meanings`, every value the
    workflow reports, in its order, with the title and unit a page names it
    by, falling back to its name, a value a sealed step holds back left out
    until the reveal. `status` is in the contestant's words: `queued` until
    its run is started, `grading` while it is graded, `graded` once it has
    a result, `delayed` while it has none and its grading failed on the
    platform's side, `over_limit` once it was to be graded again with no
    room left under the task's most submissions, and `cancelled` once staff
    end it; organisers read the grading's own status in the gradings
    routes. A `delayed` one carries nothing else: it is tried again once by
    itself, and then waits for staff, who grade it again or end it: then it
    is `cancelled`, with `reason`, the sentence they gave, which is null on
    every other status. A delayed one is graded again only while its
    entrant's submissions with a result, those waiting that are not
    delayed, and the delayed ones made before it are fewer than the task's
    most, so the first ones to get a result count, and otherwise it is
    `over_limit`, with `limit`,
    the most it reached ("Not graded: you had reached the limit of 10
    submissions for this task."), and nothing else; `limit` is null on every
    other status. While a sealed step's stop is held to the reveal, nothing
    of the run is shown: every group reads as hidden. A task graded test by
    test gives no points (stage 5).

    A run task's grading has no groups and no `values`: `run_values` holds
    each value of its scoring its entrant is shown, worked out on every
    read, and `runs` the runs, those listed under `now` from the start,
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
    `delayed`. A run task's grading whose runs failed for the platform is
    `delayed` with the runs it gave, a value reading one of its failed early
    runs `waiting`. These are empty on every other task.
    `reveal_at` is when the task reveals, until then, as what its entrant
    reads changes then with no grading's change to say so, so a page open
    on it reads it again then, as at a group's `shown_at`; null on every
    other task and once it has revealed.
    """

    status: SubmissionState
    reveal_at: datetime | None = None


class OrganisedResult(Scored):
    """A submission's grading as organisers read it beside the grading
    itself: the payload its contestant reads, with everything filled in as
    once the task has revealed, so every group's outcome and tests and every
    value a sealed step reported are there. Each group's `shown_at` is kept as a note of when its
    contestant is shown it, null once they see its tests. `status` is the
    grading's own, as in the gradings routes. On a run task, every value
    and run is there at once, each value with when it shows and what it
    read, and `facts` holds `seconds_late`, `seconds` and `compiled` as the
    values read them.
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
