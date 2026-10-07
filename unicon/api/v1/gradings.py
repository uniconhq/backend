"""An organiser's view of and controls over a task's gradings: the list of
them, newest first, each with where it stands and why it failed, and a
grading's run log, which need the observer role at the task; and, with the
manager role there, cancelling one that is not finished, at the CI too when
a run of it is there; retrying a finished one as a new attempt against the
publication it graded against, a stuck one included, whose old run is
cancelled; and rejudging every submission's latest attempt against the
task's current publication.

A grading is named by its id under its task's prefix, which is where the
guard reads the scope the role is checked at, as for every other organiser
route. A grading of any other task is no such grading here, whatever roles
the caller holds there, so a path names one grading of one task or nothing.
Forge checks the role again at the grading's own task.

A log is plain text that the browser is told not to guess the type of and
that runs nothing, so a log is never rendered as a page of the platform's.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response
from forge.api import gradings, tasks
from forge.api.access import Organiser
from forge.api.errors import NotFound
from forge.api.types import Role, ScopeKind

from unicon.api.guard import PREFIX, require
from unicon.schemas.gradings import Grading, Rejudged

TASK = PREFIX[ScopeKind.TASK]

router = APIRouter(prefix=TASK, tags=["gradings"])

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
    summary="Stop a grading that is not finished",
    response_model=Grading,
)
async def cancel_grading(organiser: TaskManager, grading: uuid.UUID) -> gradings.GradingRecord:
    """The grading as it now stands, `cancelled`, one that reads as a system
    error because its run is overdue or lost included. A finished one is
    `wrong_status`, carrying its status as `current`.
    """
    return await gradings.cancel(organiser, await _of_this_task(organiser, grading))


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


async def _of_this_task(organiser: Organiser, grading: uuid.UUID) -> uuid.UUID:
    """The grading, when it is one of the task the path names. `not_found`
    for one of another task, the same as for none at all.
    """
    if await gradings.task_of(grading) != tasks.task_id_of(organiser.scope):
        raise NotFound(NO_SUCH_GRADING)
    return grading
