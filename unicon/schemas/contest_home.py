"""What a signed-in person reads of the contests they may see: the list, a
contest's home and a task's page. Every time is the server's, and `now` on
the home is the server's clock when it was read, so a countdown agrees with
the deadline the server enforces.
"""

from datetime import datetime
from typing import Literal

from forge.api.contest_home import ContestantInput as ContestantInputRecord
from forge.api.contest_home import ContestHome as ContestHomeRecord
from forge.api.contest_home import ContestSummary as ContestSummaryRecord
from forge.api.contest_home import Limits as LimitsRecord
from forge.api.contest_home import TaskEntry as TaskEntryRecord
from forge.api.contest_home import TaskPage as TaskPageRecord
from forge.api.types import scope_of_place
from pydantic import BaseModel

from unicon.schemas.contestants import MyRegistration, Status
from unicon.schemas.contests import TaskRelease

Visibility = Literal["public", "signed-in", "hidden"]
State = Literal["draft", "published", "archived"]


class ContestSummary(BaseModel):
    """A contest the caller sees, by its org and name, with its title, when
    it runs, who sees it, and the caller's own registration status.
    """

    org: str
    name: str
    title: str
    start: datetime
    end: datetime
    visibility: Visibility
    status: Status | None

    @classmethod
    def of(cls, summary: ContestSummaryRecord) -> ContestSummary:
        scope = scope_of_place(summary.contest)
        return cls(
            org=scope.org,
            name=str(scope.contest),
            title=summary.name,
            start=summary.start,
            end=summary.end,
            visibility=summary.visibility.value,
            status=summary.status.value if summary.status is not None else None,
        )


class TaskEntry(BaseModel):
    """A task released to the caller: its name, the label and points the
    contest gives it, its title, and whether they may submit to it now.
    """

    name: str
    label: str
    title: str
    points: int | None
    release: TaskRelease

    @classmethod
    def of(cls, entry: TaskEntryRecord) -> TaskEntry:
        return cls(
            name=entry.name,
            label=entry.label,
            title=entry.title,
            points=entry.points,
            release=TaskRelease.of(entry.release),
        )


class ContestHome(BaseModel):
    """A contest's home for the caller. `organises` says the caller holds a
    role at the contest, which keeps them from registering; `registration_open`
    says whether the registration window is open now, `invite_only` whether only invited
    people may register and `asks_code` whether registering takes the
    contest's code. `deadline` is the contest's end plus the caller's own
    extension.
    """

    org: str
    name: str
    title: str
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

    @classmethod
    def of(cls, home: ContestHomeRecord) -> ContestHome:
        scope = scope_of_place(home.contest)
        return cls(
            org=scope.org,
            name=str(scope.contest),
            title=home.name,
            description=home.description,
            start=home.start,
            end=home.end,
            state=home.state.value,
            submissions_closed=home.submissions_closed,
            registration=(
                MyRegistration.of(home.registration) if home.registration is not None else None
            ),
            organises=home.organises,
            registration_open=home.registration_open,
            invite_only=home.invite_only,
            asks_code=home.asks_code,
            deadline=home.deadline,
            now=home.now,
            tasks=[TaskEntry.of(entry) for entry in home.tasks],
        )


class Limits(BaseModel):
    """What a submit is checked against: how many submissions in all, at
    most `rate_count` in any `rate_seconds`, and how large, in bytes.
    """

    submissions: int
    rate_count: int
    rate_seconds: int
    max_size: int

    @classmethod
    def of(cls, limits: LimitsRecord) -> Limits:
        return cls(
            submissions=limits.submissions,
            rate_count=limits.rate.count,
            rate_seconds=int(limits.rate.per.total_seconds()),
            max_size=limits.max_size,
        )


InputType = Literal["code", "text", "number", "boolean", "file", "file[]", "dataset", "jupyter"]


class ContestantInput(BaseModel):
    """One input the contestant gives, with what its form shows: `label`,
    the `language` choices of a code input, `min` and `max` of a number,
    the `accept` patterns and `max_size` in bytes of a file, and a
    `default`. The submit panel shows one field or drop zone per input.
    """

    id: str
    type: InputType
    label: str
    language: list[str] | None
    min: float | None
    max: float | None
    accept: list[str] | None
    max_size: int | None
    default: str | float | bool | None

    @classmethod
    def of(cls, entry: ContestantInputRecord) -> ContestantInput:
        return cls(
            id=entry.id,
            type=entry.type.value,
            label=entry.label or entry.id,
            language=list(entry.language) if entry.language is not None else None,
            min=entry.min,
            max=entry.max,
            accept=list(entry.accept) if entry.accept is not None else None,
            max_size=entry.max_size,
            default=entry.default,
        )


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

    @classmethod
    def of(cls, page: TaskPageRecord) -> TaskPage:
        return cls(
            name=page.name,
            label=page.label,
            title=page.title,
            points=page.points,
            statement=page.statement,
            limits=Limits.of(page.limits),
            inputs=[ContestantInput.of(entry) for entry in page.inputs],
            release=TaskRelease.of(page.release),
        )
