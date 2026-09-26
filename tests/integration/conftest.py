"""The app over a real Postgres and the in-memory forge, the way
`UNICON_FORGE=fake` runs it. `UNICON_TEST_DATABASE_URL` names a server these
tests may create databases on; without it they are skipped.
"""

import os
import uuid
from collections.abc import AsyncIterator, Iterator
from urllib.parse import parse_qs, urlsplit

import httpx
import psycopg
import pytest
from fastapi import FastAPI
from forge.db.migrations import upgrade_to_head
from forge.forges.fake import FakeForge
from forge.runtime import Runtime
from forge.settings import Settings

from unicon.main import create_app

SERVER_URL_VARIABLE = "UNICON_TEST_DATABASE_URL"
APP_URL = "http://app.test"
FORGE_URL = "http://forge.test"
ORIGIN = {"Origin": APP_URL}


def _server_url() -> str:
    url = os.environ.get(SERVER_URL_VARIABLE)
    if not url:
        pytest.skip(f"{SERVER_URL_VARIABLE} is not set")
    return url


def _connect(url: str) -> psycopg.Connection[tuple[object, ...]]:
    return psycopg.connect(url.replace("postgresql+psycopg://", "postgresql://"), autocommit=True)


@pytest.fixture
def database_url() -> Iterator[str]:
    server_url = _server_url()
    name = f"unicon_test_{uuid.uuid4().hex[:12]}"
    with _connect(server_url) as connection:
        connection.execute(f'CREATE DATABASE "{name}"')
    try:
        yield server_url.rsplit("/", 1)[0] + "/" + name
    finally:
        with _connect(server_url) as connection:
            connection.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')


@pytest.fixture
def migrated_database_url(database_url: str) -> str:
    upgrade_to_head(database_url)
    return database_url


@pytest.fixture
def settings(migrated_database_url: str) -> Settings:
    return Settings.for_tests(
        database_url=migrated_database_url,
        public_url=APP_URL,
        forge_public_url=FORGE_URL,
        forge_internal_url=FORGE_URL,
    )


@pytest.fixture
def forge(settings: Settings) -> FakeForge:
    fake = FakeForge(public_url=FORGE_URL, sign_in_redirect_uri=f"{APP_URL}/api/v1/auth/callback")
    fake.add_user(7, "ada", name="Ada Lovelace", email="ada@example.test")
    fake.add_user(8, "bob")
    fake.signed_in_user_id = 7
    return fake


@pytest.fixture
async def app(settings: Settings, forge: FakeForge) -> AsyncIterator[FastAPI]:
    runtime = Runtime.build(settings, forge=forge)
    built = create_app(settings, runtime)
    async with built.router.lifespan_context(built):
        yield built


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url=APP_URL) as client:
        yield client


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
