"""An action saves its change before it returns, so a route answers only
after the change is on disk. An action that fails, at its commit or
anywhere before, raises out of the call, and the route answers a fault
rather than the success it would have returned.
"""

from collections.abc import AsyncIterator

import httpx
import pytest
from fastapi import FastAPI
from forge.api import sessions
from forge.testing import APP_URL, FakeForge

from tests.integration.conftest import ORIGIN, sign_in
from unicon.api.cookies import SESSION_COOKIE


@pytest.fixture
async def faulting_client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    """A client that receives the 500 the app answers, rather than the
    exception the server re-raises after answering it.
    """
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url=APP_URL) as client:
        yield client


async def test_an_action_that_fails_is_answered_as_a_fault_and_not_a_success(
    faulting_client: httpx.AsyncClient, forge: FakeForge, monkeypatch: pytest.MonkeyPatch
) -> None:
    await sign_in(faulting_client, forge)

    async def commit_fails(*args: object, **kwargs: object) -> None:
        raise RuntimeError("the database went away at commit")

    monkeypatch.setattr(sessions, "revoke", commit_fails)

    answer = await faulting_client.post("/api/v1/auth/logout", headers=ORIGIN)

    assert answer.status_code == 500
    assert answer.json()["code"] == "internal_error"
    assert "set-cookie" not in answer.headers
    assert SESSION_COOKIE in faulting_client.cookies
