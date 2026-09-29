"""Every error the API answers with, as an RFC 9457 problem document. The
package's typed errors are mapped to a status code here and nowhere else, and
the error's stable code goes into the body so a client switches on it rather
than on prose. A typed error with no mapping is a fault in this table and is
answered as one.

What of the error reaches the client is decided per code. A refusal carries
its detail, because the detail is the reason the person can act on. A forge
that is down or wrongly registered, and an error this table does not know,
are answered with a fixed sentence: their detail names hosts, paths and the
forge's own words, which belong in the log and not in a browser.
"""

from http import HTTPStatus
from typing import Any, cast

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from forge.api.errors import UniconError
from forge.api.log import get_logger
from starlette.exceptions import HTTPException

from unicon.api.cookies import clear_session
from unicon.schemas.problem import PROBLEM_CONTENT_TYPE, Problem

log = get_logger(__name__)

STATUS = {
    "not_found": 404,
    "forbidden": 403,
    "conflict": 409,
    "rejected": 422,
    "forge_misconfigured": 502,
    "forge_unavailable": 503,
    "invalid_name": 422,
    "unauthenticated": 401,
    "session_expired": 401,
    "fresh_sign_in_required": 403,
    "sign_in_invalid": 400,
    "sign_in_denied": 400,
    "sole_admin": 409,
    "contestant_conflict": 409,
    "shared_workflow_owner": 409,
    "origin_mismatch": 403,
    "payload_too_large": 413,
    "admin_only": 403,
    "reserved_path": 403,
    "confirmation_required": 409,
    "invalid_definition": 422,
    "invalid_path": 422,
}
INTERNAL = 500
CLEARS_SESSION = frozenset({"unauthenticated", "session_expired"})
HTTP_CODES = {404: "not_found", 405: "method_not_allowed"}

WITHHELD_DETAIL = {
    "forge_unavailable": "The forge did not answer. Try again in a moment.",
    "forge_misconfigured": "The forge refused the platform's own registration.",
}
UNMAPPED_DETAIL = "The server failed to handle this request."


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(UniconError, _typed_error)
    app.add_exception_handler(RequestValidationError, _invalid_request)
    app.add_exception_handler(HTTPException, _http_error)
    app.add_exception_handler(Exception, _unexpected_error)


def status_of(error: UniconError) -> int:
    return STATUS.get(error.code, INTERNAL)


def problem_response(problem: Problem) -> JSONResponse:
    return JSONResponse(
        status_code=problem.status,
        content=problem.model_dump(mode="json"),
        media_type=PROBLEM_CONTENT_TYPE,
    )


def problem_for(error: UniconError) -> JSONResponse:
    """The response for a typed error: its status, its code, and as much of
    its detail as the client should see.
    """
    status = status_of(error)
    if error.code not in STATUS:
        log.error("errors.unmapped", code=error.code, detail=error.detail)
        return problem_response(
            Problem.of(code=error.code, status=status, title=_title(status), detail=UNMAPPED_DETAIL)
        )
    if error.code in WITHHELD_DETAIL:
        log.warning("errors.forge", code=error.code, detail=error.detail, **error.extra)
        return problem_response(
            Problem.of(
                code=error.code,
                status=status,
                title=_title(status),
                detail=WITHHELD_DETAIL[error.code],
            )
        )
    return problem_response(
        Problem.of(
            code=error.code, status=status, title=_title(status), detail=error.detail, **error.extra
        )
    )


def _title(status: int) -> str:
    return HTTPStatus(status).phrase


async def _typed_error(request: Request, exc: Exception) -> Response:
    error = cast(UniconError, exc)
    response = problem_for(error)
    if error.code in CLEARS_SESSION:
        clear_session(response)
    return response


async def _invalid_request(request: Request, exc: Exception) -> Response:
    error = cast(RequestValidationError, exc)
    return problem_response(
        Problem.of(
            code="validation_error",
            status=422,
            title=_title(422),
            detail="The request did not match the schema.",
            errors=_readable_errors(error),
        )
    )


async def _http_error(request: Request, exc: Exception) -> Response:
    error = cast(HTTPException, exc)
    return problem_response(
        Problem.of(
            code=HTTP_CODES.get(error.status_code, "http_error"),
            status=error.status_code,
            title=_title(error.status_code),
            detail=str(error.detail),
        )
    )


async def _unexpected_error(request: Request, exc: Exception) -> Response:
    return problem_response(
        Problem.of(
            code="internal_error",
            status=INTERNAL,
            title=_title(INTERNAL),
            detail=UNMAPPED_DETAIL,
        )
    )


def _readable_errors(exc: RequestValidationError) -> list[dict[str, Any]]:
    return [
        {
            "location": [str(part) for part in error["loc"]],
            "message": error["msg"],
            "type": error["type"],
        }
        for error in exc.errors()
    ]
