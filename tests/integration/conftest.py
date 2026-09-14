"""A real Postgres, and a Forgejo-shaped fake behind the real HTTP client.
`UNICON_TEST_DATABASE_URL` points at a server these tests may create databases
on; without it they are skipped, because a mocked database proves nothing about
a schema. The forge is faked at the socket, so the app runs the same clients it
runs in production.
"""

import os
import uuid
from collections.abc import AsyncIterator, Iterator

import httpx
import psycopg
import pytest
from fastapi import FastAPI

from tests.fakes.forge import FakeForge
from tests.fakes.forgejo_app import ADMIN_TOKEN, SwitchableTransport, forgejo_app
from tests.integration.running_app import running_app
from unicon.api.deps import admin_of, oidc_of
from unicon.db.migrations import upgrade_to_head
from unicon.forge.admin import AdminClient
from unicon.forge.http import ForgeHttp
from unicon.forge.oidc import CALLBACK_PATH, OidcClient
from unicon.settings import Settings

SERVER_URL_VARIABLE = "UNICON_TEST_DATABASE_URL"
APP_URL = "http://app.test"
FORGE_URL = "http://forge.test"


def _server_url() -> str:
    url = os.environ.get(SERVER_URL_VARIABLE)
    if not url:
        pytest.skip(f"{SERVER_URL_VARIABLE} is not set")
    return url


def _connect(url: str) -> psycopg.Connection[tuple[object, ...]]:
    return psycopg.connect(url.replace("postgresql+psycopg://", "postgresql://"), autocommit=True)


@pytest.fixture
def database_url() -> Iterator[str]:
    """An empty database, dropped when the test ends."""
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
        forge_admin_token=ADMIN_TOKEN,
    )


@pytest.fixture
def forge(settings: Settings) -> FakeForge:
    """One person, signed in on the consent page. The OAuth application is
    registered with exactly what the backend sends, so a test cannot pass with
    credentials the real forge would refuse.
    """
    fake = FakeForge(
        client_id=settings.forge_oauth_client_id,
        client_secret=settings.forge_oauth_client_secret.get_secret_value(),
        redirect_uri=str(settings.public_url).rstrip("/") + CALLBACK_PATH,
    )
    fake.add_user(7, "ada", name="Ada Lovelace", email="ada@example.test")
    fake.signed_in_user_id = 7
    return fake


@pytest.fixture
async def forge_http(forge: FakeForge) -> AsyncIterator[ForgeHttp]:
    transport = SwitchableTransport(forge, forgejo_app(forge))
    async with ForgeHttp(httpx.AsyncClient(base_url=FORGE_URL, transport=transport)) as http:
        yield http


@pytest.fixture
async def app(settings: Settings, forge_http: ForgeHttp) -> AsyncIterator[FastAPI]:
    async with running_app(settings) as built:
        built.dependency_overrides[oidc_of] = lambda: OidcClient(settings, forge_http)
        built.dependency_overrides[admin_of] = lambda: AdminClient(settings, forge_http)
        yield built


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url=APP_URL) as client:
        yield client


@pytest.fixture
async def browser(forge: FakeForge) -> AsyncIterator[httpx.AsyncClient]:
    """The person's other tab: the one talking to Forgejo."""
    transport = SwitchableTransport(forge, forgejo_app(forge))
    async with httpx.AsyncClient(transport=transport, base_url=FORGE_URL) as browsing:
        yield browsing
