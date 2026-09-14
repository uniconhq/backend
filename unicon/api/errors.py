"""Turning exceptions into RFC 9457 problem documents. Five handlers cover every
error response the API can give.
"""

from http import HTTPStatus
from typing import Any, cast

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from unicon.api.cookies import clear_session
from unicon.domain.errors import ForgeUnavailable, UniconError
from unicon.forge.errors import ForgeUnreachable
from unicon.schemas.problem import PROBLEM_CONTENT_TYPE, Problem

HTTP_CODES = {404: "not_found", 405: "method_not_allowed"}


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(UniconError, _named_error)
    app.add_exception_handler(ForgeUnreachable, _forge_unreachable)
    app.add_exception_handler(RequestValidationError, _invalid_request)
    app.add_exception_handler(HTTPException, _http_error)
    app.add_exception_handler(Exception, _unexpected_error)


def forge_is_down() -> ForgeUnavailable:
    """Services let `ForgeUnreachable` out rather than each translating it, so
    there is one answer for a forge that did not reply.
    """
    return ForgeUnavailable("The forge did not answer.")


def problem_response(problem: Problem) -> JSONResponse:
    return JSONResponse(
        status_code=problem.status,
        content=problem.model_dump(mode="json"),
        media_type=PROBLEM_CONTENT_TYPE,
    )


def _title(status: int) -> str:
    return HTTPStatus(status).phrase


async def _named_error(request: Request, exc: Exception) -> Response:
    error = cast(UniconError, exc)
    response = problem_response(
        Problem.of(
            code=error.code,
            status=error.status,
            title=_title(error.status),
            detail=error.detail,
            **error.extra,
        )
    )
    if error.clears_session:
        clear_session(response, request.app.state.settings)
    return response


async def _forge_unreachable(request: Request, exc: Exception) -> Response:
    return await _named_error(request, forge_is_down())


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
    code = HTTP_CODES.get(error.status_code, "http_error")
    return problem_response(
        Problem.of(
            code=code,
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
    """Location, message and type only. Pydantic's `ctx` can hold objects that do
    not serialise, and the input it echoes can hold what the client sent.
    """
    return [
        {
            "location": [str(part) for part in error["loc"]],
            "message": error["msg"],
            "type": error["type"],
        }
        for error in exc.errors()
    ]
