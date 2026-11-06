"""Making a task in a contest, listing the contest's tasks, by name or each
with where it stands and its timeline, where a task's files stand against
its publications, its publications, the form of the workflow it names, and
the save, which is how a task is published, and releasing a task's
results or taking a release back. Creating needs the manager role
at the contest and makes the task before it answers, and the lists the
observer role there; taking a task out of the contest and putting a withdrawn one back need the
manager role at the contest. The task's own
routes need the observer role at the task, the staff preview of a draft
`show` among them, and the save, a release and a take-back the manager
role.
Whether a task is released to the
caller needs only a session: it is what a contestant is told, and a contest
hidden from the caller answers as no such task.
"""

import dataclasses
from typing import Annotated

from fastapi import APIRouter, Depends, status
from forge.api import contests, files, publications, release, results, submissions, tasks
from forge.api.access import Organiser
from forge.api.leaderboards import EntrantOwner
from forge.api.publications import Draft, Preparing, Published
from forge.api.types import Edit, Role, ScopeKind
from forge.api.types import Named as NamedRecord

from unicon.api.deps import CurrentSession
from unicon.api.guard import PREFIX, TaskAtPath, require
from unicon.api.v1.contest_home import PICTURES
from unicon.schemas.contests import (
    CreateTask,
    ListedTask,
    Named,
    PutBack,
    Results,
    ResultsRequest,
    TakenOut,
    TakeOutRequest,
    TaskDetail,
    TaskStanding,
)
from unicon.schemas.files import DraftRuns, DraftRunsRequest, token_of
from unicon.schemas.publications import Preparation, Publication, SaveRequest, SaveResult
from unicon.schemas.submissions import ShowPreview, ShowPreviewRequest

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
    response_model=list[ListedTask],
)
async def list_tasks(organiser: ContestObserver) -> tuple[tasks.ListedTask, ...]:
    """The tasks the forge lets the caller read, by name, each with whether
    they manage it.
    """
    return await tasks.list_tasks(organiser, contests.contest_id_of(organiser.scope))


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


@router.post(
    f"{TASK}/take-out",
    operation_id="takeOutTask",
    summary="Take the task out of its contest: remove it, or withdraw it once anyone has submitted",
    response_model=TakenOut,
)
async def take_out_task(
    organiser: ContestManager, scope: TaskAtPath, body: TakeOutRequest
) -> TakenOut:
    """Needs the manager role at the contest. `confirmed` is what the
    organiser agreed to, as the task list's `take_out` said: `remove`, while
    nobody has submitted to the task, takes its entry out of the contest's
    `tasks`, so the letters after it move up, and deletes the task with its
    roles; `withdraw`, once anyone has, marks its entry `withdrawn`, so it
    keeps its letter, entrants no longer see it or submit to it and no
    leaderboard counts it, and its submissions are kept. Refused as
    `take_out_changed`, with `submissions` and `take_out` as they are now,
    when it would now do the other, and as `take_out_refused` when a
    leaderboard's column reads a task to be removed, with the titles of
    those `leaderboards`, or the settings cannot be edited line by line.
    Withdrawing a withdrawn task changes nothing.
    """
    done = await tasks.take_out(organiser, tasks.task_id_of(scope), body.confirmed)
    return TakenOut(done=done)


@router.post(
    f"{TASK}/put-back",
    operation_id="putBackTask",
    summary="Put a withdrawn task back in its contest",
    response_model=PutBack,
)
async def put_back_task(organiser: ContestManager, scope: TaskAtPath) -> PutBack:
    """Needs the manager role at the contest. Takes `withdrawn` out of the
    task's entry, after which it scores exactly as before; checked as a
    save of the contest's settings is, so what a leaderboard or a timeline
    refuses is `invalid_definition` naming `contest.yaml`. Answers the notes
    the leaderboards report, as that save does. A task not withdrawn changes
    nothing.
    """
    returned = await tasks.put_back(organiser, tasks.task_id_of(scope))
    return PutBack(notes=list(returned.notes))


@router.get(
    TASK,
    operation_id="getTask",
    summary="Where the task's files stand",
    response_model=TaskDetail,
)
async def get_task(organiser: TaskObserver) -> TaskDetail:
    """The head, the latest publication, and when the head is a draft, the
    errors that keep it from publishing, worked out again on every read;
    whether the task's results are released, with every release and
    take-back, who and when; what the caller may do there; and what a
    statement's picture may be.
    """
    state = await tasks.state(organiser, tasks.task_id_of(organiser.scope))
    given = {field.name: getattr(state, field.name) for field in dataclasses.fields(state)}
    return TaskDetail.model_validate({**given, "pictures": PICTURES}, from_attributes=True)


@router.post(
    f"{TASK}/results/release",
    operation_id="releaseTaskResults",
    summary="Release a task's results",
    response_model=Results,
)
async def release_task_results(
    organiser: TaskManager, body: ResultsRequest
) -> results.ResultsState:
    """From now on every entrant is shown what the task's `show` lists under
    `after_release`, and gradings made from now on run those runs first. Without
    `confirm`, nothing changes and the answer is `confirmation_required`
    with `action` `release` and, as its detail, what becomes visible, to
    whom, and that it can be taken back. A task already released answers as
    it stands. A task with no publication is `not_found`. The answer is
    read once the release has landed.
    """
    task = tasks.task_id_of(organiser.scope)
    await results.release(organiser, task, confirmed=body.confirm)
    return await results.state(organiser, task)


@router.post(
    f"{TASK}/results/hide",
    operation_id="hideTaskResults",
    summary="Take a release of a task's results back",
    response_model=Results,
)
async def hide_task_results(organiser: TaskManager, body: ResultsRequest) -> results.ResultsState:
    """From now on the task works as if it had never been released: what
    `after_release` lists is hidden again, gradings made from now on keep its
    runs late, and an extension is allowed again. Without `confirm`, nothing
    changes and the answer is `confirmation_required` with `action`
    `hide_again` and the warning as its detail: "Entrants may already have
    seen these results; hiding them again won't undo that." A task not
    released answers as it stands. The answer is read once the take-back
    has landed.
    """
    task = tasks.task_id_of(organiser.scope)
    await results.hide_again(organiser, task, confirmed=body.confirm)
    return await results.state(organiser, task)


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
    return await publications.list_publications(organiser, tasks.task_id_of(organiser.scope))


@router.get(
    f"{TASK}/workflow-form",
    operation_id="getTaskWorkflowForm",
    summary="The inputs of the workflow the task names",
)
async def get_task_workflow_form(organiser: TaskObserver) -> publications.WorkflowForm:
    """The workflow `task.yaml` names as it is saved now, a draft included,
    with each input it declares, in the workflow's order. A workflow
    declares no defaults; an entrant input's `default` is the task's own. A
    `task.yaml` that is missing or does not read, names no workflow or one
    that cannot be read answers with `problem`, the reason, and no inputs,
    so the form can mend it. Either way `graded` says whether the task has a
    graded submission, and `newer` names the workflow's latest version when
    it comes after the one the task names, which the task keeps until it is
    saved naming another. `text_values` names the values that give text, in
    the file's order, null when the settings cannot be read; a workflow
    output stays a number.
    """
    return await publications.workflow_form(organiser, tasks.task_id_of(organiser.scope))


@router.post(
    f"{TASK}/save",
    operation_id="saveTask",
    summary="Save the task's files, publishing them when they are valid",
    response_model=SaveResult,
)
async def save_task(organiser: TaskManager, body: SaveRequest) -> Published | Draft | Preparing:
    """A valid save publishes and one that is not is kept as a draft with its
    errors. Once the contest has started, until it is archived, every save
    that would publish something new is refused as `confirmation_required`
    unless it is confirmed or kept as a draft, with `changes`, what would
    change how the task grades, `regrades`, how many submissions it would
    grade again, and what the save does, as a published save's `effect`
    gives it: `results_change`, `summary`, `runs_again`, `scores` and
    `reading`, and `asked`, the head and latest publication it was worked
    out from. A confirmation sent with that `asked` is asked again when
    either has moved since, so a change someone made after the question is
    never published unread. A change naming an upload writes the pointer to
    the file the caller uploaded for that path; one that is not theirs for this task and
    path is `invalid_inputs`, and one whose bytes have not arrived
    `upload_not_ready`. A change with `remove: true` removes the file it
    names, with the token it was read with, a moved one being `conflict` as
    an edit's is; the state left is checked as any other, so removing a
    group's last test or a file an input names keeps the save as a draft.
    """
    return await publications.save(
        organiser,
        tasks.task_id_of(organiser.scope),
        {
            change.path: Edit(change.edit_content(), token_of(change.token))
            for change in body.changes
        },
        confirm=body.confirm,
        asked=body.asked,
        keep_as_draft=body.keep_as_draft,
        message=body.message,
    )


@router.post(
    f"{TASK}/draft-runs",
    operation_id="listTaskDraftRuns",
    summary="The runs a draft's repeat makes",
)
async def list_task_draft_runs(organiser: TaskObserver, body: DraftRunsRequest) -> DraftRuns:
    """Every combination of the draft's tuples, as a save makes the runs,
    for the task's cards while the organiser edits. Nothing is saved."""
    found = await files.draft_runs(organiser, tasks.task_id_of(organiser.scope), body.repeat)
    return DraftRuns.of(found)


@router.post(
    f"{TASK}/show-preview",
    operation_id="previewTaskShow",
    summary="What an entrant would be shown at a moment under a draft show",
    response_model=ShowPreview,
)
async def preview_task_show(
    organiser: TaskObserver, body: ShowPreviewRequest
) -> submissions.ShowPreview:
    """The task's latest publication with the draft's `show` in its place,
    read at the moment picked as its entrant would read it then: the
    submission named, or with none, what they would be shown before any,
    with `hidden` the runs staff read that the entrant would not be shown.
    The draft is checked alone against the publication, and a problem is
    `invalid_definition` at its path in `task.yaml`, under `scoring.show`,
    as the save words it. Nothing is saved. A task never published is
    `not_found`, "Publish the task to preview it.", and so is an entrant
    with no submission of that number.
    """
    owner = None if body.entrant is None else EntrantOwner(body.entrant)
    return await submissions.preview(
        organiser,
        tasks.task_id_of(organiser.scope),
        body.show,
        body.moment,
        owner,
        body.number,
    )


@router.get(
    f"{TASK}/preparation",
    operation_id="readTaskPreparation",
    summary="The task's latest package preparation",
)
async def read_preparation(organiser: TaskManager) -> Preparation:
    return Preparation.model_validate(
        await publications.preparation(organiser, tasks.task_id_of(organiser.scope)),
        from_attributes=True,
    )
