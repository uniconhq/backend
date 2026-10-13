"""What the contest and task routes take and answer with. A task's timeline
goes out as the forge's own `Timeline` says it, its numbers exactly.
"""

from datetime import datetime

from forge.api.contest_home import State
from forge.api.tasks import TakeOut
from pydantic import BaseModel

from unicon.schemas.exact import Exact
from unicon.schemas.publications import DefinitionError, Publication


class Named(BaseModel):
    """An org, a contest or a task, by the name people call it."""

    name: str


class ListedContest(BaseModel):
    """A contest in its org's list, by name, with its state, start and end as
    its settings say them, all three null when its settings cannot be read.
    """

    name: str
    state: State | None
    start: datetime | None
    end: datetime | None


class CreateContest(BaseModel):
    """A contest to make, titled `title` or, without one, its name."""

    name: str
    title: str | None = None


class CreateTask(BaseModel):
    """A task to make, titled `title` or, without one, its name."""

    name: str
    title: str | None = None


class TaskState(BaseModel):
    """Where a task's files stand: the version at their head, the latest
    publication or none, and whether the head is a draft, a state no
    publication froze. A draft carries the errors that keep it from
    publishing; a draft with none was held back, or has not been saved since
    it was made. `statement_written` says whether the latest publication
    holds a statement, there, not blank and not the starter's placeholder,
    false when nothing is published, and `head_statement_written` the same
    of the head.
    """

    head: str
    latest: Publication | None
    draft: bool
    errors: list[DefinitionError]
    statement_written: bool
    head_statement_written: bool


class Timeline(BaseModel):
    """A task's timeline in its contest, from its entry in `contest.yaml`,
    each at its default where the entry gives none: `worth`, the most
    points it gives, its groups' total unless the entry says, and none on a
    task whose latest publication gives no points or that has none;
    `release_at`, the
    contest's start unless the entry says; `due`, after which a submission
    is late, and `late_per_day`, the fraction a started late day takes off,
    1 unless the entry says, both none on a task with no due; and `closes`,
    the contest's end unless the entry says. `worth` and `late_per_day` are
    exact.
    """

    worth: Exact | None
    release_at: datetime
    due: datetime | None
    late_per_day: Exact | None
    closes: datetime


class TaskStanding(BaseModel):
    """One task of a contest as its organisers work from it: the task by
    name, its letter by its place in the contest's `tasks`, where its files
    stand as `GET <task>` gives it, and its timeline from its entry, each
    time at its default where the entry gives none: `worth`, null on a task
    that gives no points or has no publication, `release_at`, `due` and
    `late_per_day`, both null on a task with no due, and `closes`.

    `withdrawn` says the task is withdrawn from the contest: it keeps its
    place and its letter, entrants do not see it and no leaderboard counts
    it, until it is put back. `submissions` is how many submissions it has,
    any entrant's, and `take_out` what taking it out of the contest would
    do, for the dialog that asks first: `remove`, while it has none, which
    deletes it, or `withdraw`, once it has; null while it is withdrawn,
    when it can only be put back.
    """

    task: Named
    label: str
    state: TaskState
    timeline: Timeline
    withdrawn: bool
    submissions: int
    take_out: TakeOut | None


class TakeOutRequest(BaseModel):
    """What taking a task out of its contest should do, as the organiser
    confirmed it: `remove` or `withdraw`, as the task list's `take_out`
    said when the dialog asked.
    """

    confirmed: TakeOut


class TakenOut(BaseModel):
    """What taking the task out did: `remove`d it or `withdraw`n it."""

    done: TakeOut


class PutBack(BaseModel):
    """A withdrawn task put back: what each board reports of its tasks now,
    as a save of the contest's settings answers.
    """

    notes: list[str]
