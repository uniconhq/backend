"""An organiser's view of and controls over a task's gradings: the list of
them, newest first, each with where it stands and why it failed, and a
grading's run log, which need the observer role at the task; and, with the
manager role there, cancelling the latest attempt of a submission that
reads as a system error, with a sentence its contestant reads, when a
regrade would only repeat the fault; retrying a finished one as a new
attempt against the publication it graded against, a stuck one included,
whose old run is cancelled; and rejudging every submission's latest attempt
against the task's current publication.

An observer of a contest reads the gradings of all its tasks as one feed,
newest first, each with its task and who submitted it, narrowed by task,
by a contestant's username, by team and by status; and how many of them
wait for a machine, `queued` and `dispatched`, counted when asked.

A grading is named by its id under its task's prefix, which is where the
guard reads the scope the role is checked at, as for every other organiser
route. A grading of any other task is no such grading here, whatever roles
the caller holds there, so a path names one grading of one task or nothing.
Forge checks the role again at the grading's own task.

A log is plain text that the browser is told not to guess the type of and
that runs nothing, so a log is never rendered as a page of the platform's.
"""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Response
from forge.api import contests, gradings, tasks
from forge.api.access import Organiser
from forge.api.errors import NotFound
from forge.api.gradings import GradingStatus
from forge.api.types import Role, ScopeKind, TaskId

from unicon.api.guard import PREFIX, require
from unicon.schemas.gradings import CancelRequest, FeedEntry, Grading, Rejudged

CONTEST = PREFIX[ScopeKind.CONTEST]
TASK = PREFIX[ScopeKind.TASK]

router = APIRouter(prefix=TASK, tags=["gradings"])
feed = APIRouter(prefix=CONTEST, tags=["gradings"])

ContestObserver = Annotated[Organiser, Depends(require(Role.OBSERVER, ScopeKind.CONTEST))]
TaskManager = Annotated[Organiser, Depends(require(Role.MANAGER, ScopeKind.TASK))]
TaskObserver = Annotated[Organiser, Depends(require(Role.OBSERVER, ScopeKind.TASK))]
NO_SUCH_GRADING = "There is no such grading."
LIST_MOST = 500
LOG = "text/plain; charset=utf-8"
LOG_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Content-Security-Policy": "default-src 'none'; sandbox",
    "Cache-Control": "private, no-store",
}


@router.get(
    "/gradings",
    operation_id="listGradings",
    summary="The task's gradings, newest first",
    response_model=list[Grading],
)
async def list_gradings(
    organiser: TaskObserver, limit: Annotated[int, Query(ge=1, le=LIST_MOST)] = 100
) -> tuple[gradings.GradingRecord, ...]:
    """At most `limit` of the task's gradings, newest first. One whose run did
    not begin, did not report by its deadline, or was lost by the CI reads as
    `system_error` with the reason in `error`, whatever its row still says.
    """
    return await gradings.list(organiser, tasks.task_id_of(organiser.scope), limit=limit)


@router.get(
    "/gradings/{grading}/log",
    operation_id="readGradingLog",
    summary="The run log of one of the task's gradings",
    response_class=Response,
    responses={
        200: {
            "description": "The log, as the run wrote it.",
            "content": {LOG: {"schema": {"type": "string"}}},
        }
    },
)
async def read_grading_log(organiser: TaskObserver, grading: uuid.UUID) -> Response:
    """The log of the grading's run. A grading with no log is `not_found`,
    the same as one that is not there, and a log larger than the platform
    reads back is `log_too_large` with the `limit` in bytes.
    """
    content = await gradings.run_log(organiser, await _of_this_task(organiser, grading))
    return Response(content=content, media_type=LOG, headers=LOG_HEADERS)


@router.post(
    "/gradings/{grading}/cancel",
    operation_id="cancelGrading",
    summary="End a submission whose grading is a system error, saying why",
    response_model=Grading,
)
async def cancel_grading(
    organiser: TaskManager, grading: uuid.UUID, body: CancelRequest
) -> gradings.GradingRecord:
    """The grading as it now stands, `cancelled` with `cancel_reason`, the
    sentence its contestant reads; one that reads as a system error because
    its run is overdue or lost keeps that as its `error`. A sentence that is
    empty or over 500 characters is `invalid_reason`, a grading that is not
    a system error `wrong_status` with its status as `current`, and an
    earlier attempt of a submission graded again `conflict`, since the
    latest is the one to cancel.
    """
    return await gradings.cancel(organiser, await _of_this_task(organiser, grading), body.reason)


@router.post(
    "/gradings/{grading}/retry",
    operation_id="retryGrading",
    summary="Grade a finished grading again as a new attempt",
    response_model=Grading,
)
async def retry_grading(organiser: TaskManager, grading: uuid.UUID) -> gradings.GradingRecord:
    """The new attempt, queued. The old one is kept as it was, unless it reads
    as a system error only because its run is overdue or lost: then it is
    ended with that reason, and its run cancelled at the CI. One that is not
    finished is `wrong_status`, and `conflict` while another attempt of it
    is being graded.
    """
    return await gradings.retry(organiser, await _of_this_task(organiser, grading))


@router.post(
    "/rejudge",
    operation_id="rejudgeTask",
    summary="Grade every submission of the task again against its current publication",
    response_model=Rejudged,
)
async def rejudge_task(organiser: TaskManager) -> gradings.Rejudged:
    """How many new attempts it queued, and how many earlier attempts it
    cancelled first and left to finish. A task with no publication is
    `not_found`.
    """
    return await gradings.rejudge(organiser, tasks.task_id_of(organiser.scope))


@feed.get(
    "/gradings",
    operation_id="listContestGradings",
    summary="The contest's gradings as one feed, newest first",
    response_model=list[FeedEntry],
)
async def list_contest_gradings(
    organiser: ContestObserver,
    task: Annotated[str | None, Query(description="One task, by name")] = None,
    user: Annotated[
        str | None, Query(description="One contestant's own submissions, by username")
    ] = None,
    team: Annotated[uuid.UUID | None, Query(description="One team's submissions")] = None,
    status: Annotated[GradingStatus | None, Query(description="As the grading reads")] = None,
    limit: Annotated[int, Query(ge=1, le=LIST_MOST)] = 100,
) -> list[dict[str, Any]]:
    """At most `limit` gradings of the contest's tasks, newest first, every
    attempt a row of its own, so a submission graded again shows more than
    once. One whose run is overdue or lost reads as `system_error` with the
    reason, and a filter by status takes it as it reads. A task, username or
    team the contest does not have gives no rows.
    """
    contest = contests.contest_id_of(organiser.scope)
    names = {found.id: found.name for found in await tasks.list(organiser, contest)}
    task_id: TaskId | None = None
    if task is not None:
        named = {name: TaskId(id_) for id_, name in names.items()}
        if task not in named:
            return []
        task_id = named[task]
    rows = await gradings.feed(
        organiser, contest, task=task_id, user=user, team=team, status=status, limit=limit
    )
    return [
        {"grading": row.grading, "task": names.get(row.grading.task), "by": row.by} for row in rows
    ]


@feed.get(
    "/gradings/queue",
    operation_id="getContestQueueDepth",
    summary="How many of the contest's gradings wait for a machine",
)
async def get_contest_queue_depth(organiser: ContestObserver) -> gradings.QueueDepth:
    """`queued`, whose run is not started yet, and `dispatched`, whose run
    the CI holds until a machine takes it, counted when asked. One that is
    overdue or lost reads as a system error and is not counted.
    """
    return await gradings.queue_depth(organiser, contests.contest_id_of(organiser.scope))


async def _of_this_task(organiser: Organiser, grading: uuid.UUID) -> uuid.UUID:
    """The grading, when it is one of the task the path names. `not_found`
    for one of another task, the same as for none at all.
    """
    if await gradings.task_of(grading) != tasks.task_id_of(organiser.scope):
        raise NotFound(NO_SUCH_GRADING)
    return grading
