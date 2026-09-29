"""Making a task in a contest, listing the contest's tasks, following how far
making one has got, where a task's files stand against its publications,
its publications, and the save, which is how a task is published. Creating
needs the manager role at the contest and following it the observer role
there, since the task may not be there yet to hold roles of its own. The
task's own routes need the observer role at the task, and the save the
manager role. Whether a task is released to the caller needs only a
session: it is what a contestant is told, and a contest hidden from the
caller answers as no such task.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, status
from forge.api import contests, publications, release, tasks
from forge.api.access import Organiser
from forge.api.errors import NotFound
from forge.api.types import Edit, Role, Scope, ScopeKind

from unicon.api.deps import CurrentSession
from unicon.api.guard import PREFIX, TaskAtPath, require
from unicon.schemas.contests import CreateTask, Task, TaskRelease, TaskState
from unicon.schemas.files import token_of
from unicon.schemas.orgs import Provisioning
from unicon.schemas.publications import Publication, SaveRequest, SaveResult, save_result

ACCEPTED = status.HTTP_202_ACCEPTED
CONTEST = PREFIX[ScopeKind.CONTEST]
TASK = PREFIX[ScopeKind.TASK]

router = APIRouter(tags=["tasks"])

ContestObserver = Annotated[Organiser, Depends(require(Role.OBSERVER, ScopeKind.CONTEST))]
ContestManager = Annotated[Organiser, Depends(require(Role.MANAGER, ScopeKind.CONTEST))]
TaskObserver = Annotated[Organiser, Depends(require(Role.OBSERVER, ScopeKind.TASK))]
TaskManager = Annotated[Organiser, Depends(require(Role.MANAGER, ScopeKind.TASK))]


@router.post(
    f"{CONTEST}/tasks",
    operation_id="createTask",
    summary="Ask for a task to be made in the contest",
    status_code=ACCEPTED,
)
async def create_task(organiser: ContestManager, body: CreateTask) -> Provisioning:
    """Not found when the contest is not there."""
    record = await tasks.create(
        organiser, contests.contest_id_of(organiser.scope), body.name, title=body.title
    )
    return Provisioning.of(record)


@router.get(f"{CONTEST}/tasks", operation_id="listTasks", summary="The contest's tasks")
async def list_tasks(organiser: ContestObserver) -> list[Task]:
    """The tasks the forge lets the caller read, by name."""
    found = await tasks.list(organiser, contests.contest_id_of(organiser.scope))
    return [Task.of(task) for task in found]


@router.get(
    f"{TASK}/provisioning",
    operation_id="getTaskProvisioning",
    summary="How far making the task has got",
)
async def get_task_provisioning(organiser: ContestObserver, task: str) -> Provisioning:
    """Not found when nothing has asked for the task."""
    scope = organiser.scope
    record = await tasks.status(organiser, tasks.task_id_of(Scope(scope.org, scope.contest, task)))
    if record is None:
        raise NotFound(f"Nothing has asked for a task named {task!r}.")
    return Provisioning.of(record)


@router.get(TASK, operation_id="getTask", summary="Where the task's files stand")
async def get_task(organiser: TaskObserver) -> TaskState:
    """The head, the latest publication, and when the head is a draft, the
    errors that keep it from publishing, worked out again on every read.
    """
    return TaskState.of(await tasks.state(organiser, tasks.task_id_of(organiser.scope)))


@router.get(
    f"{TASK}/release",
    operation_id="getTaskRelease",
    summary="Whether the caller sees the task and may submit to it now",
)
async def get_task_release(session: CurrentSession, scope: TaskAtPath) -> TaskRelease:
    return TaskRelease.of(await release.of_task(session, tasks.task_id_of(scope)))


@router.get(
    f"{TASK}/publications",
    operation_id="listTaskPublications",
    summary="The task's publications, oldest first",
)
async def list_task_publications(organiser: TaskObserver) -> list[Publication]:
    found = await publications.list(organiser, tasks.task_id_of(organiser.scope))
    return [Publication.of(publication) for publication in found]


@router.post(
    f"{TASK}/save",
    operation_id="saveTask",
    summary="Save the task's files, publishing them when they are valid",
)
async def save_task(organiser: TaskManager, body: SaveRequest) -> SaveResult:
    """A valid save publishes and one that is not is kept as a draft with its
    errors. While the contest runs, a save that changes how the task grades
    is refused as `confirmation_required` unless it is confirmed or kept as a
    draft.
    """
    result = await publications.save(
        organiser,
        tasks.task_id_of(organiser.scope),
        {change.path: Edit(change.data(), token_of(change.token)) for change in body.changes},
        confirm=body.confirm,
        keep_as_draft=body.keep_as_draft,
        message=body.message,
    )
    return save_result(result)
