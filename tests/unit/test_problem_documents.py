"""Every error response is an RFC 9457 problem document with a stable code."""

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from unicon.domain.errors import NotFoundError, UniconError
from unicon.main import create_app
from unicon.schemas.problem import PROBLEM_CONTENT_TYPE
from unicon.settings import Settings


class TeapotError(UniconError):
    code = "teapot"
    status = 418


@pytest.fixture
def app(settings: Settings) -> FastAPI:
    built = create_app(settings)

    @built.get("/boom")
    async def boom() -> None:
        raise TeapotError("I am a teapot.", vessel="teapot")

    @built.get("/missing")
    async def missing() -> None:
        raise NotFoundError("No such thing.")

    @built.get("/count")
    async def count(how_many: int) -> int:
        return how_many

    return built


@pytest.fixture
async def client(app: FastAPI) -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def test_a_named_error_becomes_a_problem_document(client: AsyncClient) -> None:
    response = await client.get("/boom")

    assert response.status_code == 418
    assert response.headers["content-type"].startswith(PROBLEM_CONTENT_TYPE)
    assert response.json() == {
        "type": "about:blank",
        "title": "I'm a Teapot",
        "status": 418,
        "detail": "I am a teapot.",
        "code": "teapot",
        "vessel": "teapot",
    }


async def test_a_missing_thing_is_not_found(client: AsyncClient) -> None:
    response = await client.get("/missing")

    assert response.status_code == 404
    assert response.json()["code"] == "not_found"


async def test_an_unknown_route_is_not_found(client: AsyncClient) -> None:
    response = await client.get("/api/v1/no-such-endpoint")

    assert response.status_code == 404
    assert response.headers["content-type"].startswith(PROBLEM_CONTENT_TYPE)
    assert response.json()["code"] == "not_found"


async def test_a_bad_request_is_a_validation_error(client: AsyncClient) -> None:
    response = await client.get("/count", params={"how_many": "seven"})

    body = response.json()
    assert response.status_code == 422
    assert body["code"] == "validation_error"
    assert body["errors"][0]["location"] == ["query", "how_many"]
    assert "input" not in body["errors"][0]
