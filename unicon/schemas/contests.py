"""What the contest and task routes take and answer with, beyond the
provisioning record they share with orgs.
"""

from typing import Literal

from forge.api.release import TaskRelease as TaskReleaseRecord
from forge.api.tasks import TaskState as TaskStateRecord
from forge.api.types import ContestId, TaskId, scope_of_place
from pydantic import BaseModel

from unicon.schemas.publications import DefinitionError, Publication


class CreateContest(BaseModel):
    """A contest to make, titled `title` or, without one, its name."""

    name: str
    title: str | None = None


class CreateTask(BaseModel):
    """A task to make, titled `title` or, without one, its name."""

    name: str
    title: str | None = None


class Contest(BaseModel):
    name: str

    @classmethod
    def of(cls, contest: ContestId) -> Contest:
        return cls(name=str(scope_of_place(contest).contest))


class Task(BaseModel):
    name: str

    @classmethod
    def of(cls, task: TaskId) -> Task:
        return cls(name=str(scope_of_place(task).task))


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

    @classmethod
    def of(cls, state: TaskStateRecord) -> TaskState:
        return cls(
            head=state.head,
            latest=Publication.of(state.latest) if state.latest is not None else None,
            draft=state.draft,
            errors=[DefinitionError.of(problem) for problem in state.errors],
        )


class TaskRelease(BaseModel):
    """Whether the caller sees the task and may submit to it now, by the
    server's clock: `released` once the contest is published and started,
    the task's `release_at` has passed and it is not hidden; `visible` from
    then until the contest is archived; `open` while visible, before the
    contest's end plus the caller's own extension, with submissions not
    closed. `closed` is the first reason it is not open.
    """

    released: bool
    visible: bool
    open: bool
    closed: Literal["not_released", "archived", "ended", "submissions_closed"] | None

    @classmethod
    def of(cls, release: TaskReleaseRecord) -> TaskRelease:
        return cls(
            released=release.released,
            visible=release.visible,
            open=release.open,
            closed=release.closed.value if release.closed is not None else None,
        )
