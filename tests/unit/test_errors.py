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

from unicon.api.errors import status_of
from unicon.api.v1.events import PayloadTooLarge
from unicon.main import create_app

FORGE_DETAIL = "/api/v1/repos/acme/spring.contest/contents/x answered 500"

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
    (PayloadTooLarge, 413),
]


@pytest.mark.parametrize(("error", "status"), CASES)
def test_each_error_has_its_own_status(error: type[UniconError], status: int) -> None:
    assert status_of(error("no")) == status


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
