"""Making a task in a contest, listing the contest's tasks, by name or each
with where it stands and its timeline, where a task's files stand against
its publications, its publications, the form of the workflow it names, and
the save, which is how a task is published. Creating needs the manager role
at the contest and makes the task before it answers, and the lists the
observer role there. The task's own routes need the observer role at the
task, and the save the manager role. Whether a task is released to the
caller needs only a session: it is what a contestant is told, and a contest
hidden from the caller answers as no such task.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, status
from forge.api import contests, publications, release, tasks
from forge.api.access import Organiser
from forge.api.publications import Draft, Published
from forge.api.types import Edit, Role, ScopeKind
from forge.api.types import Named as NamedRecord

from unicon.api.deps import CurrentSession
from unicon.api.guard import PREFIX, TaskAtPath, require
from unicon.schemas.contests import CreateTask, Named, TaskStanding, TaskState
from unicon.schemas.files import token_of
from unicon.schemas.publications import Publication, SaveRequest, SaveResult

CREATED = status.HTTP_201_CREATED
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
    summary="Make a task in the contest",
    status_code=CREATED,
    response_model=Named,
)
async def create_task(organiser: ContestManager, body: CreateTask) -> NamedRecord:
    """Not found when the contest is not there."""
    return await tasks.create(
        organiser, contests.contest_id_of(organiser.scope), body.name, title=body.title
    )


@router.get(
    f"{CONTEST}/tasks",
    operation_id="listTasks",
    summary="The contest's tasks",
    response_model=list[Named],
)
async def list_tasks(organiser: ContestObserver) -> tuple[NamedRecord, ...]:
    """The tasks the forge lets the caller read, by name."""
    return await tasks.list(organiser, contests.contest_id_of(organiser.scope))


@router.get(
    f"{CONTEST}/organise/tasks",
    operation_id="listTaskStandings",
    summary="The contest's tasks in its order, each with where it stands and its timeline",
    response_model=list[TaskStanding],
)
async def list_task_standings(organiser: ContestObserver) -> tuple[tasks.TaskStanding, ...]:
    """Every task the contest's `tasks` lists, in that order, each with its
    letter, its latest publication, whether a draft sits on it and the
    draft's errors, and its timeline. A task the contest does not list is
    not here. Settings that do not read are `invalid_definition`, naming
    `contest.yaml`, with every one of its `errors` at its path.
    """
    return await tasks.standing(organiser, contests.contest_id_of(organiser.scope))


@router.get(
    TASK,
    operation_id="getTask",
    summary="Where the task's files stand",
    response_model=TaskState,
)
async def get_task(organiser: TaskObserver) -> tasks.TaskState:
    """The head, the latest publication, and when the head is a draft, the
    errors that keep it from publishing, worked out again on every read.
    """
    return await tasks.state(organiser, tasks.task_id_of(organiser.scope))


@router.get(
    f"{TASK}/release",
    operation_id="getTaskRelease",
    summary="Whether the caller sees the task and may submit to it now",
)
async def get_task_release(session: CurrentSession, scope: TaskAtPath) -> release.TaskRelease:
    return await release.of_task(session, tasks.task_id_of(scope))


@router.get(
    f"{TASK}/publications",
    operation_id="listTaskPublications",
    summary="The task's publications, oldest first",
    response_model=list[Publication],
)
async def list_task_publications(organiser: TaskObserver) -> tuple[publications.Publication, ...]:
    return await publications.list(organiser, tasks.task_id_of(organiser.scope))


@router.get(
    f"{TASK}/workflow-form",
    operation_id="getTaskWorkflowForm",
    summary="The inputs and test fields of the workflow the task names",
)
async def get_task_workflow_form(organiser: TaskObserver) -> publications.WorkflowForm:
    """The workflow `task.yaml` names as it is saved now, a draft included,
    with each input it declares and each field every test has, in the
    workflow's order. A workflow declares no defaults; a contestant input's
    `default` is the task's own. A `task.yaml` that is missing or does not
    read, names no workflow or one that cannot be read answers with
    `problem`, the reason, and no inputs, so the form can mend it. Either
    way `graded` says whether the task has a graded submission, from when
    on a save refuses a test group it adds without its `show`, and `newer`
    names the workflow's latest version when it comes after the one the
    task names, which the task keeps until it is saved naming another.
    """
    return await publications.workflow_form(organiser, tasks.task_id_of(organiser.scope))


@router.post(
    f"{TASK}/save",
    operation_id="saveTask",
    summary="Save the task's files, publishing them when they are valid",
    response_model=SaveResult,
)
async def save_task(organiser: TaskManager, body: SaveRequest) -> Published | Draft:
    """A valid save publishes and one that is not is kept as a draft with its
    errors. While the contest runs, a save that changes how the task grades
    is refused as `confirmation_required` unless it is confirmed or kept as a
    draft. A change naming an upload writes the pointer to the file the
    caller uploaded for that path; one that is not theirs for this task and
    path is `invalid_inputs`, and one whose bytes have not arrived
    `upload_not_ready`.
    """
    return await publications.save(
        organiser,
        tasks.task_id_of(organiser.scope),
        {
            change.path: Edit(change.edit_content(), token_of(change.token))
            for change in body.changes
        },
        confirm=body.confirm,
        keep_as_draft=body.keep_as_draft,
        message=body.message,
    )
