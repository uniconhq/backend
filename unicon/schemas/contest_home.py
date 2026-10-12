"""What a signed-in person reads of the contests they may see: the list, a
contest's home and a task's page. A contest is `where` it is, by the names
of its org and itself, and `name` is its title. Every time is the server's,
and `now` on the home is the server's clock when it was read, so a countdown
agrees with the times the server enforces.
"""

import dataclasses
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from forge.api.contest_home import ContestVisibility, State
from forge.api.entrants import Status
from forge.api.release import TaskRelease
from pydantic import BaseModel, model_validator

from unicon.schemas.entrants import MyEntry
from unicon.schemas.exact import Exact, exactly
from unicon.schemas.submissions import Points, Value


class ContestNames(BaseModel):
    """A contest by the names of its org and itself."""

    org: str
    contest: str


class ContestSummary(BaseModel):
    """A contest the caller sees, with its title, when it runs, who sees it,
    and the status of the caller's entrant, null when they are in none.
    """

    where: ContestNames
    name: str
    start: datetime
    end: datetime
    visibility: ContestVisibility
    status: Status | None


class TaskEntry(BaseModel):
    """A task released to the caller: its name, the label its place in the
    contest gives it, its title, the most points it gives, null on a task
    that gives none, whether they may submit to it now, and when it falls
    due, null when it has no due, and closes for them, their extension on it
    included.

    `points` is their entrant's points on it, for a member of an approved
    entrant, as a board over that task alone counts them now, every group,
    the best submission by points: `shown`, over the groups whose results
    are shown, and `pending`, the most the groups not shown yet could still
    add, until `pending_until`, the task's reveal, null when nothing is
    pending. A group whose results are not shown yet never counts in
    `shown`, as on every board. Null for anyone else, and on a task that
    gives no points.
    """

    name: str
    label: str
    title: str
    worth: Exact | None
    release: TaskRelease
    due: datetime | None
    closes: datetime | None
    points: Points | None


class ContestHome(BaseModel):
    """A contest's home for the caller. `organises` says the caller holds a
    role at the contest, which keeps them from registering; `registration`
    is their registration panel, as `entrants/mine` answers it: their
    entrant, whether and how they may register, and whether to ask them for
    a code.
    """

    where: ContestNames
    name: str
    description: str
    start: datetime
    end: datetime
    state: State
    registration: MyEntry
    organises: bool
    now: datetime
    tasks: list[TaskEntry]


class Rate(BaseModel):
    """At most `count` submissions in any `per` seconds."""

    count: int
    per: int


class Submissions(BaseModel):
    """What a submit is counted against: at most `max` submissions in all,
    and at most `rate` of them in any window.
    """

    max: int
    rate: Rate


InputType = Literal["text", "number", "boolean", "enum", "file", "folder"]
"""The types a contestant input has."""


class InputField(BaseModel):
    """One input the contestant gives, with what its form shows: its
    `type`, its `label`, the `options` of an enum, whether it takes one file
    per test, `per_test`, named for the test as `<group>/<test>`, the
    `default` a value takes when it is left out, `min` and `max` of a
    number, exactly, and `max_size`, the most its files may total in bytes. A
    number input's default is served as its exact digits, as its bounds are.
    The submit panel shows one field or drop zone per input.
    """

    id: str
    type: InputType
    label: str
    options: list[str] | None
    per_test: bool
    default: Value | None
    min: Exact | None
    max: Exact | None
    max_size: int

    @model_validator(mode="before")
    @classmethod
    def _exact_default(cls, given: Any) -> Any:
        # A route answers forge's own `Field`, read by its attributes; a test
        # or a client gives a dict.
        if dataclasses.is_dataclass(given) and not isinstance(given, type):
            given = {each.name: getattr(given, each.name) for each in dataclasses.fields(given)}
        found = given if isinstance(given, dict) else None
        if found is None or found.get("type") != "number":
            return given
        default = found.get("default")
        if isinstance(default, int | float | Decimal) and not isinstance(default, bool):
            return {**found, "default": exactly(default)}
        return given


class TaskPage(BaseModel):
    """A task as the caller reads it: its statement in Markdown, the caps a
    submit is counted against, the inputs a contestant gives, when it falls
    due and closes for them, and `marks`, how many of their entrant's
    submissions they may mark for the `marked` boards, null unless such a
    board covers the task and their entrant is approved; and nothing
    else the task holds.
    """

    name: str
    label: str
    title: str
    worth: Exact | None
    statement: str
    submissions: Submissions
    inputs: list[InputField]
    release: TaskRelease
    due: datetime | None
    closes: datetime | None
    marks: int | None
