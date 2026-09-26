"""The app over a real Postgres and the in-memory forge, the way
`UNICON_FORGE=fake` runs it.
"""

from collections.abc import AsyncIterator
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from fastapi import FastAPI
from forge.forges.fake import FakeForge
from forge.runtime import Runtime
from forge.testing import APP_URL

from unicon.main import create_app
from unicon.settings import ShellSettings

ORIGIN = {"Origin": APP_URL}


@pytest.fixture
def settings(migrated_database_url: str) -> ShellSettings:
    return ShellSettings.for_tests(
        database_url=migrated_database_url, public_url=APP_URL, forge_public_url="http://forge.test"
    )


@pytest.fixture
async def app(settings: ShellSettings, runtime: Runtime) -> AsyncIterator[FastAPI]:
    built = create_app(settings, runtime)
    async with built.router.lifespan_context(built):
        yield built


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url=APP_URL) as client:
        yield client


@pytest.fixture
def forge(fake: FakeForge) -> FakeForge:
    return fake


async def sign_in(
    client: httpx.AsyncClient, forge: FakeForge, next_path: str = "/"
) -> httpx.Response:
    """The three hops of a sign-in as the browser makes them. Returns the
    callback response, which carries the session cookie.
    """
    started = await client.get("/api/v1/auth/login", params={"next": next_path})
    assert started.status_code == 302
    return await client.get(forge.consent_redirect(started.headers["location"]))


def query_of(response: httpx.Response) -> dict[str, list[str]]:
    return parse_qs(urlsplit(response.headers["location"]).query)
