"""A contestant's submissions of a task: submitting the uploads and values
they give, and reading their own submissions back, each with its grading at
every stage as the task shows it, the files one was made with, and its run
log where the stage shows everything. Each needs
a session and no role. Forge reads only the caller's own: anyone else's
submission is no such submission, the same as one that is not there.

A submission's file is answered as its bytes, as a download: the content
type says nothing about what the bytes are, the browser is told not to guess,
and nothing in them runs, so a file a contestant uploaded is never rendered
as a page of the platform's. A log is plain text under the same headers.
"""

from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Path, Query, Response, status
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
DOWNLOAD = "application/octet-stream"
LOG = "text/plain; charset=utf-8"
DOWNLOAD_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Content-Security-Policy": "default-src 'none'; sandbox",
    "Cache-Control": "private, no-store",
}

router = APIRouter(prefix=f"{TASK}/submissions", tags=["submissions"])

Number = Annotated[int, Path(ge=1, le=NUMBER_MAX, description="The submission's number")]


@router.post(
    "",
    operation_id="createSubmission",
    summary="Submit the caller's uploads and values to the task",
    status_code=CREATED,
)
async def create_submission(
    session: CurrentSession, scope: TaskAtPath, body: SubmitRequest
) -> Submission:
    """The new submission, its grading queued at each stage graded on
    submit. The same `idempotency_key` sent again answers with the
    submission it made and makes nothing. A submit the task's rules refuse
    answers with the rule's code, such as `rate_limited` with `retry_at` or
    `submission_limit` with `limit`, before anything is written.
    """
    submission = await submissions.submit(
        session,
        tasks.task_id_of(scope),
        {input: given.record() for input, given in body.inputs.items()},
        idempotency_key=body.idempotency_key,
    )
    return Submission.of(submission)


@router.get(
    "",
    operation_id="listMySubmissions",
    summary="The caller's own submissions of the task, newest first",
)
async def list_my_submissions(session: CurrentSession, scope: TaskAtPath) -> list[Submission]:
    found = await submissions.mine(session, tasks.task_id_of(scope))
    return [Submission.of(submission) for submission in found]


@router.get(
    "/{number}",
    operation_id="getMySubmission",
    summary="One of the caller's own submissions of the task",
)
async def get_my_submission(
    session: CurrentSession, scope: TaskAtPath, number: Number
) -> Submission:
    """With what each stage's `show` lets the caller see of its grading."""
    return Submission.of(await submissions.one(session, tasks.task_id_of(scope), number))


@router.get(
    "/{number}/files",
    operation_id="listMySubmissionFiles",
    summary="What one of the caller's own submissions was made with",
)
async def list_my_submission_files(
    session: CurrentSession, scope: TaskAtPath, number: Number
) -> SubmittedFiles:
    """Each input's files by their paths in the submission, its language, or
    its value, so a page can put them back into the upload panel.
    """
    return SubmittedFiles.of(await submissions.files(session, tasks.task_id_of(scope), number))


@router.get(
    "/{number}/files/{path:path}",
    operation_id="readMySubmissionFile",
    summary="One file of one of the caller's own submissions, as a download",
    response_class=Response,
    responses={
        200: {
            "description": "The file's bytes.",
            "content": {DOWNLOAD: {"schema": {"type": "string", "format": "binary"}}},
        }
    },
)
async def read_my_submission_file(
    session: CurrentSession, scope: TaskAtPath, number: Number, path: str
) -> Response:
    """`path` is one of the paths the files route names, such as
    `files/submission/main.py`.
    """
    content = await submissions.file(session, tasks.task_id_of(scope), number, path)
    return Response(
        content=content,
        media_type=DOWNLOAD,
        headers={**DOWNLOAD_HEADERS, "Content-Disposition": _attachment(path)},
    )


@router.get(
    "/{number}/log",
    operation_id="readMySubmissionLog",
    summary="The run log of one of the caller's own submissions",
    response_class=Response,
    responses={
        200: {
            "description": "The log, as the run wrote it.",
            "content": {LOG: {"schema": {"type": "string"}}},
        }
    },
)
async def read_my_submission_log(
    session: CurrentSession,
    scope: TaskAtPath,
    number: Number,
    stage: Annotated[
        str | None, Query(description="A stage; the first with a log when absent")
    ] = None,
) -> Response:
    """The log of the latest attempt at the stage, only where the stage's
    `show` is `full`; anywhere else it is `not_found`, the same as a
    submission that is not the caller's.
    """
    content = await submissions.run_log(session, tasks.task_id_of(scope), number, stage=stage)
    return Response(content=content, media_type=LOG, headers=DOWNLOAD_HEADERS)


def _attachment(path: str) -> str:
    """A download named after the file's own name, the last segment of its
    path, quoted for the header when it is not plain.
    """
    name = path.rsplit("/", 1)[-1]
    quoted = quote(name, safe="")
    if quoted == name:
        return f'attachment; filename="{name}"'
    return f"attachment; filename*=UTF-8''{quoted}"
