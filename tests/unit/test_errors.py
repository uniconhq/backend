"""Each of the package's typed errors comes out with its own status and code,
in one place, and an unmapped one still carries its code.
"""

import pytest
from forge.domain import errors
from forge.domain.errors import UniconError
from forge.settings import Settings
from httpx import ASGITransport, AsyncClient

from unicon.api.errors import status_of
from unicon.main import create_app

CASES = [
    (errors.NotFound, 404),
    (errors.Forbidden, 403),
    (errors.Conflict, 409),
    (errors.Rejected, 422),
    (errors.Unavailable, 503),
    (errors.Unauthenticated, 401),
    (errors.SessionExpired, 401),
    (errors.FreshSignInRequired, 403),
    (errors.SignInInvalid, 400),
    (errors.SignInDenied, 400),
    (errors.Misconfigured, 502),
    (errors.SoleAdmin, 409),
    (errors.SharedWorkflowOwner, 409),
]


@pytest.mark.parametrize(("error", "status"), CASES)
def test_each_error_has_its_own_status(error: type[UniconError], status: int) -> None:
    assert status_of(error("no")) == status


class Surprise(UniconError):
    code = "surprise"


def test_an_unmapped_error_keeps_its_code() -> None:
    assert status_of(Surprise("no")) == 400


async def test_a_typed_error_becomes_a_problem_document(settings: Settings) -> None:
    app = create_app(settings)

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


async def test_an_unauthenticated_answer_clears_the_cookie(settings: Settings) -> None:
    app = create_app(settings)

    @app.get("/who")
    async def who() -> None:
        raise errors.Unauthenticated("No session.")

    transport = ASGITransport(app=app)
    cookies = {"unicon_session": "x"}
    async with AsyncClient(transport=transport, base_url="http://test", cookies=cookies) as client:
        response = await client.get("/who")

    assert response.status_code == 401
    assert "unicon_session=" in response.headers["set-cookie"]
    assert "max-age=0" in response.headers["set-cookie"].lower()
