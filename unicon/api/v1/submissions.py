"""A contestant's submissions of a task: submitting the uploads and values
they give, and reading their own submissions back, each with its grading as
the task's test groups show it, and the files one was made with. Each needs
a session and no role. Forge reads only the caller's own: anyone else's
submission is no such submission, the same as one that is not there. A
run's log names every test, hidden ones too, so it is the organisers'
alone.

A submission's files are downloaded through the download door
(`unicon/api/door.py`), so their bytes never pass through here.

A run task's result shows where each text a step wrote is, a run's label,
message and texts and the steps done once's that `show` lists, the
compile log among them, but never the stored output that holds it, which may be another entrant's
and says when it was made. The caller reads one at a time by where it is
shown, a run's group and place, or neither for the steps done once, and
the text, and only while their result shows it to them; any other is no
such text. A text is plain text the browser is told not to guess the type
of and that runs nothing, as a run log is.
"""

from typing import Annotated, Literal

from fastapi import APIRouter, Path, Query, Response, status
from forge.api import submissions, tasks
from forge.api.submissions import TextAt
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
Output = Annotated[
    str, Path(max_length=64, description="The stored output that holds the text, as named")
]
TextName = Annotated[str, Path(max_length=255, description="The text's name in that output")]
TEXT = "text/plain; charset=utf-8"
TEXT_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Content-Security-Policy": "default-src 'none'; sandbox",
    "Cache-Control": "private, no-store",
}
TEXT_RESPONSES: dict[int | str, dict[str, object]] = {
    200: {
        "description": "The text, as the step wrote it.",
        "content": {TEXT: {"schema": {"type": "string"}}},
    }
}


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


@router.get(
    "/{number}/text",
    operation_id="readMySubmissionText",
    summary="A text one of the caller's own submissions shows them",
    response_class=Response,
    responses=TEXT_RESPONSES,
)
async def read_my_submission_text(
    session: CurrentSession,
    scope: TaskAtPath,
    number: Number,
    group: Annotated[
        str | None,
        Query(max_length=255, description="The group the run is shown under; none for once"),
    ] = None,
    place: Annotated[
        int | None,
        Query(ge=1, le=NUMBER_MAX, description="The run's place in that group, from 1"),
    ] = None,
    field: Annotated[
        Literal["texts", "label", "message"],
        Query(description="`texts` for a text by its name, or the run's label or message"),
    ] = "texts",
    name: Annotated[
        str | None, Query(max_length=255, description="The text's name, under `texts`")
    ] = None,
) -> Response:
    """A text the submission's result shows the caller now, where it shows
    it: a run's, by the group and place it is shown at, or the steps done
    once's, with neither. Any other is `not_found`, the same as one that
    is not there.
    """
    found = await submissions.read_text(
        session, tasks.task_id_of(scope), number, TextAt(group, place, field, name)
    )
    return Response(content=found, media_type=TEXT, headers=TEXT_HEADERS)
