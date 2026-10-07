"""A contestant's submissions of a task: submitting the uploads and values
they give, and reading their own submissions back, each with its grading as
the task's test groups show it, and the files one was made with. Each needs
a session and no role. Forge reads only the caller's own: anyone else's
submission is no such submission, the same as one that is not there. A
run's log names every test, hidden ones too, so it is the organisers'
alone.

A submission's files are downloaded through the download door
(`unicon/api/door.py`), so their bytes never pass through here.
"""

from typing import Annotated

from fastapi import APIRouter, Path, status
from forge.api import submissions, tasks
from forge.api.types import ScopeKind

from unicon.api.deps import CurrentSession
from unicon.api.guard import PREFIX, TaskAtPath
from unicon.schemas.submissions import Submission, SubmitRequest, SubmittedFiles

CREATED = status.HTTP_201_CREATED
TASK = PREFIX[ScopeKind.TASK]
NUMBER_MAX = 2**31 - 1
"""The largest number a submission can have, the most the database's
integer holds, so a larger one is refused before forge is asked."""

router = APIRouter(prefix=f"{TASK}/submissions", tags=["submissions"])

Number = Annotated[int, Path(ge=1, le=NUMBER_MAX, description="The submission's number")]


@router.post(
    "",
    operation_id="createSubmission",
    summary="Submit the caller's uploads and values to the task",
    status_code=CREATED,
    response_model=Submission,
)
async def create_submission(
    session: CurrentSession, scope: TaskAtPath, body: SubmitRequest
) -> submissions.Submission:
    """The new submission, its grading queued. The same `idempotency_key`
    sent again answers with the submission it made and makes nothing. A
    submit the task's rules refuse answers with the rule's code, such as
    `rate_limited` with `retry_at` or `submission_limit` with `limit`,
    before anything is written.
    """
    return await submissions.submit(
        session, tasks.task_id_of(scope), body.inputs, idempotency_key=body.idempotency_key
    )


@router.get(
    "",
    operation_id="listMySubmissions",
    summary="The caller's own submissions of the task, newest first",
    response_model=list[Submission],
)
async def list_my_submissions(
    session: CurrentSession, scope: TaskAtPath
) -> tuple[submissions.Submission, ...]:
    return await submissions.mine(session, tasks.task_id_of(scope))


@router.get(
    "/{number}",
    operation_id="getMySubmission",
    summary="One of the caller's own submissions of the task",
    response_model=Submission,
)
async def get_my_submission(
    session: CurrentSession, scope: TaskAtPath, number: Number
) -> submissions.Submission:
    """With what the task's test groups let the caller see of its grading
    now.
    """
    return await submissions.one(session, tasks.task_id_of(scope), number)


@router.get(
    "/{number}/files",
    operation_id="listMySubmissionFiles",
    summary="What one of the caller's own submissions was made with",
    response_model=SubmittedFiles,
)
async def list_my_submission_files(
    session: CurrentSession, scope: TaskAtPath, number: Number
) -> submissions.SubmittedFiles:
    """Each input's files by their paths in the submission, or its value;
    each file downloads through the download door.
    """
    return await submissions.files(session, tasks.task_id_of(scope), number)
