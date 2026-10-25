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
    and the values its steps reported for it. Scored, it carries its credit,
    from 0 to 1, and, on a relative credit, the best value that credit is
    measured against; both are null otherwise.
    """

    test: str
    outcome: Outcome
    values: Reported
    credit: Exact | None = None
    best: Exact | None = None


class RunShown(BaseModel):
    """One run of a run task's grading as its entrant sees it: the group
    `show` lists that shows it, its place in that group from 1 ("Test 3"),
    its key as the plan gives it, leaving out a file not yet shown, its
    verdict, `passed`, 1 when that is `accepted`, and the numbers its steps
    reported, exactly. A run in two groups shown is shown in each. Its
    texts stay out until an entrant's route reads them. Organisers read
    every run, under `all` in the task's order, with its `id`, which
    counts every run of the task; `id` is null for an entrant.
    """

    group: str
    place: int
    id: str | None = None
    key: dict[str, Any]
    verdict: Outcome
    passed: int
    reports: dict[str, Exact]


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
    """Points as a contestant sees them, a submission's or their entrant's on
    a task: those shown, null while no group's verdict is shown yet, so a
    shown 0 reads apart from nothing shown; those still pending on groups
    whose verdict is not shown yet; and when they are shown, null when none
    are pending.
    """

    shown: Exact | None
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
    limit: int | None
    meanings: list[ValueMeaning]
    runs: list[RunShown] = []


class Result(Scored):
    """The attempt of a submission's grading that counts, as its contestant
    sees it: the latest that finished with a result, as the boards count
    it, so a regrade under way, a failure or a cancel leaves the result as
    it was, and while none has, the latest. Its id, attempt and status, and
    once it is done, what stopped the
    run, the outcome over the groups shown, each test group as its `show`
    allows, the values reported once, and `folded`, each per-test value
    with a fold, folded over the tests shown, a test that was not accepted
    or did not report it counting as its worst bound, and the value absent
    when it declares none, so a wrong answer has no time; each test's row
    still carries what it reported; and `meanings`, every value the
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
    other status.
    Once done on a task that gives points, it carries
    its `points` and the late `factor` they include; both are null
    otherwise. While a sealed step's stop is held to the reveal, nothing of
    the run is shown: every group reads as hidden.

    A run task's grading has no groups or values yet, which its scoring
    makes in a later stage: `runs` holds the runs its entrant is shown,
    those of the groups `show` lists under `now` from the start, and those
    under `after_close` once the task reveals; a group under `on_release`
    shows none yet. After the reveal, while those are still being graded, it
    is `grading` or `delayed`. `runs` is empty on every other task.
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
    """One submission of an entrant, as organisers read it: its number
    among the entrant's, when it was taken, how many started days late, and
    its grading with everything filled in.
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
