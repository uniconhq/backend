"""What a signed-in person reads of the contests they may see: the list, a
contest's home and a task's page. A contest is `where` it is, by the names
of its org and itself, and `name` is its title. Every time is the server's,
and `now` on the home is the server's clock when it was read, so a countdown
agrees with the times the server enforces.
"""

from datetime import datetime
from typing import Literal

from forge.api.contest_home import ContestVisibility, State
from forge.api.contestants import Status
from forge.api.release import TaskRelease
from pydantic import BaseModel

from unicon.schemas.contestants import MyRegistration
from unicon.schemas.exact import Exact
from unicon.schemas.submissions import Value


class ContestNames(BaseModel):
    """A contest by the names of its org and itself."""

    org: str
    contest: str


class ContestSummary(BaseModel):
    """A contest the caller sees, with its title, when it runs, who sees it,
    and the caller's own registration status.
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
    """

    name: str
    label: str
    title: str
    worth: Exact | None
    release: TaskRelease
    due: datetime | None
    closes: datetime | None


class ContestHome(BaseModel):
    """A contest's home for the caller. `organises` says the caller holds a
    role at the contest, which keeps them from registering;
    `registration_open` says whether the registration window is open now,
    `invite_only` whether only invited people may register and `asks_code`
    whether registering takes the contest's code.
    """

    where: ContestNames
    name: str
    description: str
    start: datetime
    end: datetime
    state: State
    registration: MyRegistration | None
    organises: bool
    registration_open: bool
    invite_only: bool
    asks_code: bool
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
    number, and `max_size`, the most its files may total in bytes. The
    submit panel shows one field or drop zone per input.
    """

    id: str
    type: InputType
    label: str
    options: list[str] | None
    per_test: bool
    default: Value | None
    min: int | float | None
    max: int | float | None
    max_size: int


class TaskPage(BaseModel):
    """A task as the caller reads it: its statement in Markdown, the caps a
    submit is counted against, the inputs a contestant gives, and when it
    falls due and closes for them, and nothing else the task holds.
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
