"""An organiser's controls over a task's gradings: cancelling one that is not
finished, at the CI too when a run of it is there; retrying a finished one as
a new attempt against the publication it graded against; and rejudging every
submission's latest attempt against the task's current publication. Each
needs the manager role at the task.

A grading is named by its id under its task's prefix, which is where the
guard reads the scope the role is checked at, as for every other organiser
route. A grading of any other task is no such grading here, whatever roles
the caller holds there, so a path names one grading of one task or nothing.
Forge checks the role again at the grading's own task.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from forge.api import gradings, tasks
from forge.api.access import Organiser
from forge.api.errors import NotFound
from forge.api.types import Role, ScopeKind

from unicon.api.guard import PREFIX, require
from unicon.schemas.gradings import Grading, Rejudged

TASK = PREFIX[ScopeKind.TASK]

router = APIRouter(prefix=TASK, tags=["gradings"])

TaskManager = Annotated[Organiser, Depends(require(Role.MANAGER, ScopeKind.TASK))]
NO_SUCH_GRADING = "There is no such grading."


@router.post(
    "/gradings/{grading}/cancel",
    operation_id="cancelGrading",
    summary="Stop a grading that is not finished",
    response_model=Grading,
)
async def cancel_grading(organiser: TaskManager, grading: uuid.UUID) -> gradings.GradingRecord:
    """The grading as it now stands, `cancelled`. A finished one is
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
    """The new attempt, queued; the old one is kept as it was. One that is
    not finished is `wrong_status`, and `conflict` while another attempt of
    it is being graded.
    """
    return await gradings.retry(organiser, await _of_this_task(organiser, grading))


@router.post(
    "/rejudge",
    operation_id="rejudgeTask",
    summary="Grade every submission of the task again against its current publication",
    response_model=Rejudged,
)
async def rejudge_task(organiser: TaskManager) -> gradings.Rejudged:
    """How many new attempts it queued, cancelled first, left to finish and
    passed over. A task with no publication is `not_found`.
    """
    return await gradings.rejudge(organiser, tasks.task_id_of(organiser.scope))


async def _of_this_task(organiser: Organiser, grading: uuid.UUID) -> uuid.UUID:
    """The grading, when it is one of the task the path names. `not_found`
    for one of another task, the same as for none at all.
    """
    if await gradings.task_of(grading) != tasks.task_id_of(organiser.scope):
        raise NotFound(NO_SUCH_GRADING)
    return grading
