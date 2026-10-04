"""What a signed-in person reads of the contests they may see: the list, a
contest's home and a task's page. A contest is `where` it is, by the names
of its org and itself, and `name` is its title. Every time is the server's,
and `now` on the home is the server's clock when it was read, so a countdown
agrees with the deadline the server enforces.
"""

from datetime import datetime

from forge.api.contest_home import ContestVisibility, InputType, State
from forge.api.contestants import Status
from forge.api.release import TaskRelease
from pydantic import BaseModel

from unicon.schemas.contestants import MyRegistration, Seconds


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
    """A task released to the caller: its name, the label and points the
    contest gives it, its title, and whether they may submit to it now.
    """

    name: str
    label: str
    title: str
    points: int | None
    release: TaskRelease


class ContestHome(BaseModel):
    """A contest's home for the caller. `organises` says the caller holds a
    role at the contest, which keeps them from registering;
    `registration_open` says whether the registration window is open now,
    `invite_only` whether only invited people may register and `asks_code`
    whether registering takes the contest's code. `deadline` is the
    contest's end plus the caller's own extension.
    """

    where: ContestNames
    name: str
    description: str
    start: datetime
    end: datetime
    state: State
    submissions_closed: bool
    registration: MyRegistration | None
    organises: bool
    registration_open: bool
    invite_only: bool
    asks_code: bool
    deadline: datetime
    now: datetime
    tasks: list[TaskEntry]


class Rate(BaseModel):
    """At most `count` submissions in any `per` seconds."""

    count: int
    per: Seconds


class Limits(BaseModel):
    """What a submit is checked against: how many submissions in all, how
    often, and how large, in bytes.
    """

    submissions: int
    rate: Rate
    max_size: int


class ContestantInput(BaseModel):
    """One input the contestant gives, with what its form shows: `label`,
    the `language` choices of a code input, `min` and `max` of a number,
    the `accept` patterns and `max_size` in bytes of a file, and a
    `default`. The submit panel shows one field or drop zone per input, and
    an input with no label by its id.
    """

    id: str
    type: InputType
    label: str | None
    language: list[str] | None
    min: float | None
    max: float | None
    accept: list[str] | None
    max_size: int | None
    default: str | float | bool | None


class TaskPage(BaseModel):
    """A task as the caller reads it: its statement in Markdown, the limits
    a submit is checked against and the inputs a contestant gives, and
    nothing else the task holds.
    """

    name: str
    label: str
    title: str
    points: int | None
    statement: str
    limits: Limits
    inputs: list[ContestantInput]
    release: TaskRelease
