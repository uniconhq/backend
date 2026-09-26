"""Every error the API answers with, as an RFC 9457 problem document. The
package's typed errors are mapped to a status code here and nowhere else, and
the error's stable code goes into the body so a client switches on it rather
than on prose.
"""

from http import HTTPStatus
from typing import Any, cast

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from forge.domain.errors import UniconError
from starlette.exceptions import HTTPException

from unicon.api.cookies import clear_session
from unicon.schemas.problem import PROBLEM_CONTENT_TYPE, Problem

STATUS = {
    "not_found": 404,
    "forbidden": 403,
    "conflict": 409,
    "rejected": 422,
    "forge_unavailable": 503,
    "unauthenticated": 401,
    "session_expired": 401,
    "fresh_sign_in_required": 403,
    "sign_in_invalid": 400,
    "sign_in_denied": 400,
    "forge_misconfigured": 502,
    "sole_admin": 409,
    "shared_workflow_owner": 409,
    "origin_mismatch": 403,
}
UNMAPPED_STATUS = 400
CLEARS_SESSION = frozenset({"unauthenticated", "session_expired"})
HTTP_CODES = {404: "not_found", 405: "method_not_allowed"}


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(UniconError, _typed_error)
    app.add_exception_handler(RequestValidationError, _invalid_request)
    app.add_exception_handler(HTTPException, _http_error)
    app.add_exception_handler(Exception, _unexpected_error)


def status_of(error: UniconError) -> int:
    return STATUS.get(error.code, UNMAPPED_STATUS)


def problem_response(problem: Problem) -> JSONResponse:
    return JSONResponse(
        status_code=problem.status,
        content=problem.model_dump(mode="json"),
        media_type=PROBLEM_CONTENT_TYPE,
    )


def _title(status: int) -> str:
    return HTTPStatus(status).phrase


async def _typed_error(request: Request, exc: Exception) -> Response:
    error = cast(UniconError, exc)
    status = status_of(error)
    response = problem_response(
        Problem.of(
            code=error.code, status=status, title=_title(status), detail=error.detail, **error.extra
        )
    )
    if error.code in CLEARS_SESSION:
        clear_session(response, request.app.state.settings)
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
            status=500,
            title=_title(500),
            detail="The server failed to handle this request.",
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
