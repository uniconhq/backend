"""The unit of work commits before the response leaves. A commit that fails
is answered as a fault, never as the success the route returned.
"""

from collections.abc import AsyncIterator

import httpx
import pytest
from fastapi import FastAPI, Response, status
from forge.runtime import Runtime
from forge.testing import APP_URL

from tests.integration.conftest import ORIGIN
from unicon.api.deps import Db
from unicon.main import create_app
from unicon.settings import ShellSettings


async def _refuse_to_commit() -> None:
    raise RuntimeError("the database went away at commit")


@pytest.fixture
async def failing_app(settings: ShellSettings, runtime: Runtime) -> AsyncIterator[FastAPI]:
    built = create_app(settings, runtime)

    @built.post("/commit-fails", status_code=status.HTTP_204_NO_CONTENT)
    async def commit_fails(db: Db) -> Response:
        db.commit = _refuse_to_commit  # type: ignore[method-assign]
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    async with built.router.lifespan_context(built):
        yield built


async def test_a_commit_that_fails_is_not_answered_as_a_success(failing_app: FastAPI) -> None:
    transport = httpx.ASGITransport(app=failing_app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url=APP_URL) as client:
        answer = await client.post("/commit-fails", headers=ORIGIN)

    assert answer.status_code == 500
    assert answer.json()["code"] == "internal_error"
