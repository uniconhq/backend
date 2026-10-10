"""The three doors a grading run calls, with no session and no browser: the
CI's configuration extension, where the CI asks what a run's steps are; the
envelope the harness fetches when the run begins; and the callback it
reports through. Each hands forge the request as it arrived, since what
admits it is over its exact bytes: the CI's signature over the target and
the body, the envelope key in the query, and the run's bearer token. The
Origin check lets the two that change state through, and a body is read
only up to a bound, as at the event door.

Nothing here logs the `Authorization` header or the envelope's `key`: the
request log records the path and never the query or a header. The public
proxy answers the configuration extension with 404, as it does the event
door, so only the CI inside the stack reaches it.
"""

import uuid
from typing import Any

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse
from forge.api import runs

from unicon.api import raw
from unicon.schemas.gradings import CallbackAnswer

MAX_CONFIG_BODY = 1024 * 1024
MAX_CALLBACK_BODY = 4 * 1024 * 1024
"""A finished report carries the result with a row for every test, so its
bound is wider than the CI's question."""
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
    runs.ENVELOPE_PATH,
    operation_id="getGradingEnvelope",
    summary="The envelope a grading run fetches as it begins",
    responses={
        200: {"description": "The runner's `envelope.schema.json`.", "content": JSON_OBJECT}
    },
)
async def get_grading_envelope(grading: uuid.UUID, key: str = "") -> JSONResponse:
    """The runner's `envelope.schema.json`, for the envelope key the URL
    carries. It is served once, while the grading is dispatched, and that
    fetch is the run beginning. A wrong key is `not_found`, and a second
    fetch, a grading the CI holds no run of, or one whose deadline has
    passed, `grading_closed`. It carries the run's callback token, so it is
    never stored on the way.
    """
    envelope: dict[str, Any] = await runs.envelope(grading, key)
    return JSONResponse(envelope, headers=NO_STORE)


@router.post(
    runs.CALLBACK_PATH,
    operation_id="reportGradingRun",
    summary="A grading run reports how it stands",
    openapi_extra=_raw_body(
        "`started`, `progress` with `step`, `done` and `total`, or `finished` with `result`."
    ),
)
async def report_grading_run(request: Request, grading: uuid.UUID) -> CallbackAnswer:
    """Under `Authorization: Bearer <token>`, the run's own token: `started`,
    `progress` with the step and its counts, or `finished` with the result.
    A missing or wrong token is `invalid_token`, a body that is no report
    `invalid_callback`, and a grading that takes no reports now
    `grading_closed`. The same result sent again is answered the same.
    """
    body = await raw.body(request, MAX_CALLBACK_BODY, "A report")
    status = await runs.callback(grading, request.headers.get("authorization"), body)
    return CallbackAnswer(status=status)
