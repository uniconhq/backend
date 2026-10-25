"""The marks a row holds on a task, and marking or unmarking a submission."""

from fastapi import APIRouter
from forge.api import marks, tasks
from forge.api.types import ScopeKind

from unicon.api.deps import CurrentSession
from unicon.api.guard import PREFIX, TaskAtPath
from unicon.api.v1.submissions import Number
from unicon.schemas.marks import Marks

router = APIRouter(tags=["marks"])

TASK = PREFIX[ScopeKind.TASK]


@router.get(
    f"{TASK}/marks",
    operation_id="getMyMarks",
    summary="The marks the caller's row holds on the task",
    response_model=Marks,
)
async def get_my_marks(session: CurrentSession, scope: TaskAtPath) -> marks.Marks:
    return await marks.held(session, tasks.task_id_of(scope))


@router.put(
    f"{TASK}/marks/{{number}}",
    operation_id="markSubmission",
    summary="Mark one of the row's own submissions to the task",
    response_model=Marks,
)
async def mark_submission(
    session: CurrentSession, scope: TaskAtPath, number: Number
) -> marks.Marks:
    """Marking a submission already marked changes nothing."""
    return await marks.mark(session, tasks.task_id_of(scope), number)


@router.delete(
    f"{TASK}/marks/{{number}}",
    operation_id="unmarkSubmission",
    summary="Take the mark off one of the row's submissions to the task",
    response_model=Marks,
)
async def unmark_submission(
    session: CurrentSession, scope: TaskAtPath, number: Number
) -> marks.Marks:
    """Taking off a mark the submission does not have changes nothing."""
    return await marks.unmark(session, tasks.task_id_of(scope), number)
