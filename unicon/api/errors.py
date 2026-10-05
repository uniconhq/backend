"""Every error the API answers with, as an RFC 9457 problem document. The
package's typed errors are mapped to a status code here and nowhere else, and
the error's stable code goes into the body so a client switches on it rather
than on prose. A typed error with no mapping is a fault in this table and is
answered as one.

What of the error reaches the client is decided per code. A refusal carries
its detail, because the detail is the reason the person can act on. A forge
that is down or wrongly registered, and an error this table does not know,
are answered with a fixed sentence: their detail names hosts, paths and the
forge's own words, which belong in the log and not in a browser. A member of
an error's refusal never replaces a field of the document itself, such as its
`status`; one that would is left out and logged. A refusal that says when
to try again, `rate_limited`, says it in a `Retry-After` header too.
"""

from datetime import UTC, datetime, timedelta
from email.utils import format_datetime
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
    "registration_closed": 403,
    "is_staff": 403,
    "invite_required": 403,
    "wrong_invite_code": 403,
    "domain_not_allowed": 403,
    "already_registered": 409,
    "contest_full": 409,
    "invalid_invite": 422,
    "already_invited": 409,
    "invite_expired": 410,
    "teams_off": 409,
    "invalid_team_name": 422,
    "team_name_taken": 409,
    "team_full": 409,
    "in_team": 409,
    "submitted_alone": 409,
    "team_has_submissions": 409,
    "team_changed": 409,
    "invite_limit": 429,
    "wrong_status": 409,
    "invalid_message": 422,
    "invalid_reason": 422,
    "invalid_extension": 422,
    "task_closed": 403,
    "archived": 403,
    "not_approved": 403,
    "submission_limit": 409,
    "rate_limited": 429,
    "too_large": 413,
    "upload_not_yours": 404,
    "upload_not_ready": 409,
    "upload_limit": 409,
    "log_too_large": 409,
    "invalid_inputs": 422,
    "invalid_idempotency_key": 422,
    "ci_request_refused": 403,
    "invalid_token": 401,
    "grading_closed": 410,
    "invalid_callback": 422,
}
INTERNAL = 500
CLEARS_SESSION = frozenset({"unauthenticated", "session_expired"})
RETRY_AFTER = frozenset({"rate_limited", "invite_limit"})
HTTP_CODES = {404: "not_found", 405: "method_not_allowed"}

WITHHELD_DETAIL = {
    "forge_unavailable": "The forge did not answer. Try again in a moment.",
    "forge_misconfigured": "The forge refused the platform's own registration.",
}
UNMAPPED_DETAIL = "The server failed to handle this request."
DOCUMENT_FIELDS = frozenset(Problem.model_fields)


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
        log.warning("errors.forge", code=error.code, detail=error.detail, extra=error.extra)
        return problem_response(
            Problem.of(
                code=error.code,
                status=status,
                title=_title(status),
                detail=WITHHELD_DETAIL[error.code],
            )
        )
    extra = {key: value for key, value in error.extra.items() if key not in DOCUMENT_FIELDS}
    if len(extra) < len(error.extra):
        log.error(
            "errors.member_clash",
            code=error.code,
            members=sorted(error.extra.keys() - extra.keys()),
        )
    response = problem_response(
        Problem.of(
            code=error.code, status=status, title=_title(status), detail=error.detail, **extra
        )
    )
    retry_after = _retry_after(error)
    if retry_after is not None:
        response.headers["Retry-After"] = retry_after
    return response


def _retry_after(error: UniconError) -> str | None:
    """When a refusal that says when to try again may be tried again, as the
    HTTP date of `retry_at`, rounded up to the second so a client that waits
    for it is not early. None for any other refusal, or a `retry_at` that
    does not read as a time with its zone.
    """
    if error.code not in RETRY_AFTER:
        return None
    value = error.extra.get("retry_at")
    try:
        moment = datetime.fromisoformat(value) if isinstance(value, str) else None
    except ValueError:
        moment = None
    if moment is None or moment.tzinfo is None:
        return None
    if moment.microsecond:
        moment = moment.replace(microsecond=0) + timedelta(seconds=1)
    return format_datetime(moment.astimezone(UTC), usegmt=True)


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
