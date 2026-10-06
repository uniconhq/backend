"""An organiser's view of and controls over a task's gradings: the list of
them, newest first, each with where it stands and why it failed, which
needs the observer role at the task; and, with the manager role there,
cancelling one that is not finished, at the CI too when a run of it is
there; retrying a finished one as a new attempt against the publication it
graded against, a stuck one included, whose old run is cancelled; and
rejudging every submission's latest attempt against the task's current
publication.

A grading is named by its id under its task's prefix, which is where the
guard reads the scope the role is checked at, as for every other organiser
route. A grading of any other task is no such grading here, whatever roles
the caller holds there, so a path names one grading of one task or nothing.
Forge checks the role again at the grading's own task.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
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
