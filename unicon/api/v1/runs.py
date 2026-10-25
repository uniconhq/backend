"""The doors a grading run calls, with no session and no browser: the CI's
configuration extension, where the CI asks what a pipeline's steps are;
and a step's door, where each Woodpecker step asks for its job, its upload
links and the files the forge serves it, says it is done, and the
pipeline's last step reports. Each hands forge the request as it arrived,
since what admits it is over its exact bytes: the CI's signature over the
target and the body, and the step's bearer token. The Origin check lets
those that change state through, and a body is read only up to a bound,
as at the event door.

Nothing here logs the `Authorization` header: the request log records the
path and never the query or a header. The public proxy answers the
configuration extension with 404, as it does the event door, so only the
CI inside the stack reaches it.
"""

import uuid
from typing import Any

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse
from forge.api import runs

from unicon.api import raw
from unicon.schemas.gradings import CallbackAnswer

MAX_CONFIG_BODY = 1024 * 1024
MAX_UPLOADS_BODY = 16 * 1024 * 1024
"""A step lists at most 10,000 files, each path at most 1,024 bytes in
UTF-8."""
MAX_STEP_BODY = 64 * 1024
"""A step's done and its pipeline's report carry `{}`."""
NO_STORE = {"Cache-Control": "no-store"}
JSON_OBJECT = {"application/json": {"schema": {"type": "object"}}}


def _raw_body(description: str) -> dict[str, Any]:
    """The request body of a door that reads it raw, for the document: the
    route takes it as bytes, so FastAPI cannot say what it is.
    """
    return {"requestBody": {"required": True, "description": description, "content": JSON_OBJECT}}


router = APIRouter(tags=["runs"])


@router.post(
    runs.CI_CONFIG_PATH,
    operation_id="answerCiConfig",
    summary="The CI asks what a grading run's steps are",
    response_class=Response,
    responses={
        200: {
            "description": "The run's configuration, in the media type forge gives.",
            "content": JSON_OBJECT,
        }
    },
    openapi_extra=_raw_body("The CI's question, signed over these exact bytes."),
)
async def answer_ci_config(request: Request) -> Response:
    """Signed by the CI with its key; a request that does not verify, names
    no grading, or names one not being started with these variables is
    `ci_request_refused`, never an empty answer.
    """
    body = await raw.body(request, MAX_CONFIG_BODY, "The CI's request")
    answer = await runs.config(
        runs.InboundRequest(
            method=request.method,
            target=raw.target(request),
            headers=raw.headers(request),
            body=body,
        )
    )
    return Response(content=answer.body, media_type=answer.content_type, headers=NO_STORE)


@router.get(
    runs.STEP_PATH,
    operation_id="getStepJob",
    summary="A step asks for its job",
    response_class=Response,
    responses={
        200: {"description": "The runner's `job.schema.json`.", "content": JSON_OBJECT},
        204: {"description": "Nothing is left for the step to do."},
    },
)
async def get_step_job(request: Request, grading: uuid.UUID, step: str) -> Response:
    """Under `Authorization: Bearer <token>`, the step's own token: the
    step's job, or 204 when every run of it is left out, which its wrapper
    ends on with success. A missing or wrong token, or one that no longer
    works, is `invalid_token`, and a grading that has finished
    `grading_closed`. The job carries presigned links, so it is never
    stored on the way.
    """
    job = await runs.step_job(grading, step, request.headers.get("authorization"))
    if job is None:
        return Response(status_code=204, headers=NO_STORE)
    return Response(content=job, media_type="application/json", headers=NO_STORE)


@router.post(
    runs.STEP_PATH,
    operation_id="reportStepPipeline",
    summary="A pipeline reports that it has ended",
    openapi_extra=_raw_body("`{}`, from the pipeline's report step."),
)
async def report_step_pipeline(request: Request, grading: uuid.UUID, step: str) -> CallbackAnswer:
    """Under the report step's token: the result built from what the steps
    kept and the grading finished, every token of it ended; answered the
    same when said again. A step other than the report is `not_found`.
    """
    body = await raw.body(request, MAX_STEP_BODY, "A pipeline's report")
    status = await runs.step_report(grading, step, request.headers.get("authorization"), body)
    return CallbackAnswer(status=status)


@router.post(
    runs.UPLOADS_PATH,
    operation_id="listStepUploads",
    summary="A step lists what it will upload",
    responses={
        200: {"description": "A presigned PUT for each file listed.", "content": JSON_OBJECT}
    },
    openapi_extra=_raw_body('`{"files": [{"path", "sha256", "size"}]}`.'),
)
async def list_step_uploads(request: Request, grading: uuid.UUID, step: str) -> JSONResponse:
    """Under the step's token: `{"files": {<path>: <link>}}`, each link
    signed for the SHA-256 listed. A list naming a path the step may not
    write, over what it may write, or sent before its job is
    `invalid_callback`. The token is checked before the list is read,
    since the list can be large and the token is not over it.
    """
    authorization = request.headers.get("authorization")
    await runs.step_admits(grading, step, authorization)
    body = await raw.body(request, MAX_UPLOADS_BODY, "An upload list")
    links = await runs.step_uploads(grading, step, authorization, body)
    return JSONResponse(links, headers=NO_STORE)


@router.post(
    runs.DONE_PATH,
    operation_id="sayStepDone",
    summary="A step says its uploads are in",
    status_code=204,
    response_class=Response,
    openapi_extra=_raw_body("`{}`."),
)
async def say_step_done(request: Request, grading: uuid.UUID, step: str) -> Response:
    """Under the step's token: what it uploaded read and kept, or its fault
    noted, and its token ended. Said again, it is answered the same.
    """
    body = await raw.body(request, MAX_STEP_BODY, "A step's done")
    await runs.step_done(grading, step, request.headers.get("authorization"), body)
    return Response(status_code=204)


@router.get(
    runs.FILE_PATH,
    operation_id="getStepFile",
    summary="A file the forge serves a step",
    response_class=Response,
    responses={
        200: {
            "description": "The file, by its SHA-256.",
            "content": {"application/octet-stream": {"schema": {"type": "string"}}},
        }
    },
)
async def get_step_file(request: Request, grading: uuid.UUID, step: str, sha256: str) -> Response:
    """Under the step's token: a file its job names that the forge serves
    itself, by its SHA-256; one its job does not name is `not_found`.
    """
    content = await runs.step_file(grading, step, sha256, request.headers.get("authorization"))
    return Response(content=content, media_type="application/octet-stream", headers=NO_STORE)
