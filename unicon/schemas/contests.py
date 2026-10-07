"""What the contest and task routes take and answer with. A task's timeline
goes out as the forge's own `Timeline`.
"""

from forge.api.tasks import Timeline
from pydantic import BaseModel

from unicon.schemas.publications import DefinitionError, Publication


class Named(BaseModel):
    """An org, a contest or a task, by the name people call it."""

    name: str


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
    it was made.
    """

    head: str
    latest: Publication | None
    draft: bool
    errors: list[DefinitionError]


class TaskStanding(BaseModel):
    """One task of a contest as its organisers work from it: the task by
    name, its letter by its place in the contest's `tasks`, where its files
    stand as `GET <task>` gives it, and its timeline from its entry, each
    time at its default where the entry gives none: `worth`, null on a task
    that gives no points or has no publication, `release_at`, `due` and
    `late_per_day`, both null on a task with no due, and `closes`.
    """

    task: Named
    label: str
    state: TaskState
    timeline: Timeline
