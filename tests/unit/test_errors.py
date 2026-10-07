"""Each of the package's typed errors comes out with its own status and code,
in one place, and one the table does not know is answered as a fault. That
an unauthenticated answer clears the cookie is in the integration tests,
since the cookie's flags are forge's.
"""

import pytest
from fastapi import FastAPI
from forge.api import errors
from forge.api.errors import UniconError
from httpx import ASGITransport, AsyncClient

from unicon.api.errors import STATUS, status_of
from unicon.api.raw import PayloadTooLarge
from unicon.main import create_app

FORGE_DETAIL = "/api/v1/repos/acme/spring.contest/contents/x answered 500"
RETRY_AT = "2026-09-26T12:00:30+00:00"
UPLOAD = "0192f4a4-7b7e-7000-8000-000000000001"

CASES = [
    (errors.NotFound, 404),
    (errors.Forbidden, 403),
    (errors.Conflict, 409),
    (errors.Rejected, 422),
    (errors.Unavailable, 503),
    (errors.InvalidName, 422),
    (errors.Unauthenticated, 401),
    (errors.SessionExpired, 401),
    (errors.FreshSignInRequired, 403),
    (errors.SignInInvalid, 400),
    (errors.SignInDenied, 400),
    (errors.Misconfigured, 502),
    (errors.SoleAdmin, 409),
    (errors.ContestantConflict, 409),
    (errors.SharedWorkflowOwner, 409),
    (errors.AdminOnly, 403),
    (errors.ReservedPath, 403),
    (errors.ConfirmationRequired, 409),
    (errors.InvalidPath, 422),
    (errors.RegistrationClosed, 403),
    (errors.IsStaff, 403),
    (errors.InviteRequired, 403),
    (errors.WrongInviteCode, 403),
    (errors.DomainNotAllowed, 403),
    (errors.AlreadyRegistered, 409),
    (errors.ContestFull, 409),
    (errors.WrongStatus, 409),
    (errors.InvalidReason, 422),
    (errors.InvalidExtension, 422),
    (errors.TaskClosed, 403),
    (errors.Archived, 403),
    (errors.NotApproved, 403),
    (errors.SubmissionLimit, 409),
    (errors.RateLimited, 429),
    (errors.TooLarge, 413),
    (errors.UploadNotYours, 404),
    (errors.UploadNotReady, 409),
    (errors.InvalidInputs, 422),
    (errors.InvalidIdempotencyKey, 422),
    (errors.LogTooLarge, 409),
    (errors.CiRequestRefused, 403),
    (errors.InvalidToken, 401),
    (errors.GradingClosed, 410),
    (errors.InvalidCallback, 422),
    (PayloadTooLarge, 413),
]


@pytest.mark.parametrize(("error", "status"), CASES)
def test_each_error_has_its_own_status(error: type[UniconError], status: int) -> None:
    assert status_of(error("no")) == status


ANSWERED_ELSEWHERE = {"not_ready"}
"""Codes a route answers itself: `/readyz` turns `not_ready` into its own
503 body, so the table never sees it."""


def test_every_error_the_front_door_names_has_a_status() -> None:
    named = {
        found.code
        for found in (getattr(errors, name) for name in errors.__all__)
        if isinstance(found, type) and issubclass(found, UniconError) and "code" in vars(found)
    }

    assert named - {UniconError.code} - ANSWERED_ELSEWHERE <= STATUS.keys()


class Surprise(UniconError):
    code = "surprise"


def test_an_unmapped_error_is_a_fault() -> None:
    assert status_of(Surprise("no")) == 500


async def test_a_typed_error_becomes_a_problem_document() -> None:
    app = create_app()

    @app.get("/boom")
    async def boom() -> None:
        raise errors.SoleAdmin("Someone else first.", scopes=[{"kind": "org", "name": "acme"}])

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/boom")

    assert response.status_code == 409
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["code"] == "sole_admin"
    assert response.json()["scopes"] == [{"kind": "org", "name": "acme"}]


REFUSALS = [
    (errors.ContestantConflict("bob is a contestant.", contests=["acme/spring"]), 409, "contests"),
    (errors.AdminOnly("Only an admin may.", keys=["name", "statement.md"]), 403, "keys"),
    (errors.ReservedPath("Only the compiler.", paths=["plans/default.json"]), 403, "paths"),
    (
        errors.ConfirmationRequired("Confirm it.", changes=["plans/default.json changed"]),
        409,
        "changes",
    ),
    (
        errors.InvalidDefinition(
            "contest.yaml", [{"path": "visibility", "message": "Not a visibility."}]
        ),
        422,
        "errors",
    ),
    (errors.InvalidPath("Not a path.", path="../other.task/task.yaml"), 422, "path"),
    (errors.WrongStatus("It was rejected.", current="rejected"), 409, "current"),
    (errors.TaskClosed("It ended.", reason="ended"), 403, "reason"),
    (errors.SubmissionLimit("All made.", limit=50), 409, "limit"),
    (errors.RateLimited("Wait.", rate="1 per 30s", retry_at=RETRY_AT), 429, "retry_at"),
    (errors.TooLarge("Too big.", limit=1024, input="notes"), 413, "input"),
    (errors.UploadNotYours("Not yours.", uploads=[UPLOAD]), 404, "uploads"),
    (errors.UploadNotReady("Not there.", uploads=[UPLOAD]), 409, "uploads"),
    (errors.LogTooLarge("Too long to show.", limit=9 * 1024 * 1024), 409, "limit"),
    (
        errors.InvalidInputs("No.", errors=[{"input": "submission", "message": "No."}]),
        422,
        "errors",
    ),
]


@pytest.mark.parametrize(
    ("error", "status", "member"), REFUSALS, ids=[error.code for error, _, _ in REFUSALS]
)
async def test_a_refusal_carries_its_member(error: UniconError, status: int, member: str) -> None:
    app = create_app()

    @app.get("/refused")
    async def refused() -> None:
        raise error

    body = await _answer(app, "/refused")

    assert body["_status"] == status
    assert body["code"] == error.code
    assert body["detail"] == error.detail
    assert body[member] == error.extra[member]


async def _answer(app: FastAPI, path: str) -> dict[str, object]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(path)
    body: dict[str, object] = response.json()
    body["_status"] = response.status_code
    return body


async def test_a_member_named_like_a_field_of_the_document_is_left_out() -> None:
    app = create_app()

    @app.get("/clash")
    async def clash() -> None:
        raise errors.WrongStatus("It was rejected.", status="rejected", current="rejected")

    body = await _answer(app, "/clash")

    assert (body["_status"], body["status"], body["code"]) == (409, 409, "wrong_status")
    assert body["current"] == "rejected"


async def test_a_forge_that_is_down_is_answered_without_its_detail() -> None:
    app = create_app()

    @app.get("/down")
    async def down() -> None:
        raise errors.Unavailable(FORGE_DETAIL)

    @app.get("/wrong")
    async def wrong() -> None:
        raise errors.Misconfigured("invalid_client from /login/oauth/access_token", error="x")

    down_body = await _answer(app, "/down")
    wrong_body = await _answer(app, "/wrong")

    assert down_body["_status"] == 503
    assert down_body["code"] == "forge_unavailable"
    assert wrong_body["_status"] == 502
    assert wrong_body["code"] == "forge_misconfigured"
    for body in (down_body, wrong_body):
        assert "/api/v1" not in str(body)
        assert "/login/oauth" not in str(body)
        assert "error" not in body


async def test_an_unmapped_error_is_answered_without_its_detail() -> None:
    app = create_app()

    @app.get("/odd")
    async def odd() -> None:
        raise Surprise("internal detail about table foo")

    body = await _answer(app, "/odd")

    assert body["_status"] == 500
    assert body["code"] == "surprise"
    assert "table foo" not in str(body)


async def test_a_refusal_keeps_its_reason() -> None:
    app = create_app()

    @app.get("/refused")
    async def refused() -> None:
        raise errors.Rejected("The name is taken at the forge.")

    body = await _answer(app, "/refused")

    assert body["_status"] == 422
    assert body["detail"] == "The name is taken at the forge."


async def test_a_rate_limit_says_when_to_try_again_in_its_header_too() -> None:
    app = create_app()

    @app.get("/busy/{retry_at}")
    async def busy(retry_at: str) -> None:
        raise errors.RateLimited("Wait.", rate="1 per 30s", retry_at=retry_at)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        exact = await client.get(f"/busy/{RETRY_AT}")
        early = await client.get("/busy/2026-09-26T20:00:29.250000+08:00")
        unzoned = await client.get("/busy/2026-09-26T12:00:30")

    assert exact.status_code == 429
    assert exact.headers["retry-after"] == "Sat, 26 Sep 2026 12:00:30 GMT"
    assert early.headers["retry-after"] == "Sat, 26 Sep 2026 12:00:30 GMT"
    assert "retry-after" not in unzoned.headers
    assert unzoned.json()["retry_at"] == "2026-09-26T12:00:30"


async def test_no_other_refusal_carries_a_retry_after() -> None:
    app = create_app()

    @app.get("/closed")
    async def closed() -> None:
        raise errors.TaskClosed("It ended.", reason="ended", retry_at=RETRY_AT)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/closed")

    assert "retry-after" not in response.headers
