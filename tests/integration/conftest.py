"""The app over a real Postgres and the in-memory forge, the way
`UNICON_FORGE=fake` runs it. The test holds forge's setup through
`held_setup`, so the app is served without its lifespan, which would start
forge a second time, and moves provisioning along with `tick`, one tick of
the poller the lifespan would run.

The organiser path starts from `acme`, the org made the operator's way with
ada (7) its admin and the built-in workflow `unicon/classic@v1` public at the
fake as bootstrap makes it, and `sum_task`, the contest acme/spring and the
task acme/spring/sum in it made through the routes and the poller, with ada
signed in. `world` adds carol (20), who holds nothing. `ORG`, `CONTEST` and
`TASK` are the three scopes' URLs, and `ACME`, `SPRING` and `SUM` the scopes
themselves. `run_contest` and `publish` are the two writes a test of a
running contest starts with, and `edit_task` changes the task's settings.
`entered` adds carol as the task's approved contestant with her workspace
made, and `enter` makes anyone else one; `upload` sends a file the way the
browser does.
"""

import asyncio
import re
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from fastapi import FastAPI
from forge.api import orgs
from forge.api.types import Scope
from forge.testing import APP_URL, FakeForge, OrgName, Setup, seed_classic, tick

from unicon.cli import main
from unicon.main import create_app

ORIGIN = {"Origin": APP_URL}
ORG = "/api/v1/orgs/acme"
CONTEST = f"{ORG}/contests/spring"
TASK = f"{CONTEST}/tasks/sum"
ACME = Scope("acme")
SPRING = Scope("acme", "spring")
SUM = Scope("acme", "spring", "sum")

Command = Callable[[list[str]], Awaitable[int]]


@pytest.fixture
def app(held_setup: object) -> FastAPI:
    return create_app()


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url=APP_URL) as client:
        yield client


@pytest.fixture
def forge(fake: FakeForge) -> FakeForge:
    return fake


@pytest.fixture
def unicon(held_setup: Setup, monkeypatch: pytest.MonkeyPatch) -> Command:
    """`unicon` as the operator runs it, over the test's forge. The command
    starts forge and stops it; here starting finds the test's setup already
    held, stopping stops that setup on the command's own loop, and logging
    is left to pytest. The command runs its own event loop, so it runs on a
    thread of its own beside the test's.
    """
    monkeypatch.setattr("forge.api.start", lambda **options: None)
    monkeypatch.setattr("forge.api.stop", held_setup.stop)
    monkeypatch.setattr("forge.api.log.setup", lambda: None)

    async def run(argv: list[str]) -> int:
        return await asyncio.to_thread(main, argv)

    return run


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


async def sign_in_as(client: httpx.AsyncClient, forge: FakeForge, user_id: int) -> None:
    """Sign the client in as the user, in place of whoever it was."""
    forge.signed_in_user_id = user_id
    await sign_in(client, forge)


@pytest.fixture
async def acme(forge: FakeForge, held_setup: Setup) -> FakeForge:
    """acme, made the operator's way with ada its admin, and the built-in
    workflow public at the fake.
    """
    record = await orgs.create_by_operator(
        OrgName("acme"), description="Acme", admin_username="ada"
    )
    assert record.status == "ready"
    await seed_classic(forge)
    forge.reset_calls()
    return forge


@pytest.fixture
async def sum_task(client: httpx.AsyncClient, acme: FakeForge, held_setup: Setup) -> FakeForge:
    """acme/spring and acme/spring/sum made through the routes, each followed
    through the poller, with ada signed in and the task not yet saved.
    """
    await sign_in(client, acme)
    asked = await client.post(f"{ORG}/contests", json={"name": "spring"}, headers=ORIGIN)
    assert asked.status_code == 202
    await tick(held_setup, "provisioning")
    asked = await client.post(f"{CONTEST}/tasks", json={"name": "sum"}, headers=ORIGIN)
    assert asked.status_code == 202
    await tick(held_setup, "provisioning")
    acme.reset_calls()
    return acme


@pytest.fixture
def world(sum_task: FakeForge) -> FakeForge:
    """The organiser path's org, contest and task, with carol (20) holding
    nothing.
    """
    sum_task.add_user(20, "carol", name="Carol", avatar_url="http://forge.test/avatars/carol")
    return sum_task


async def read(client: httpx.AsyncClient, path: str) -> dict[str, Any]:
    """A file as the editor reads it, content and token."""
    answer = await client.get(path)
    assert answer.status_code == 200, answer.text
    body: dict[str, Any] = answer.json()
    return body


async def run_contest(client: httpx.AsyncClient, *, visibility: str = "signed-in") -> None:
    """acme/spring published and running around the fake clock, seen by
    `visibility`, written through `contest.yaml` as the signed-in organiser.
    """
    settings = await read(client, f"{CONTEST}/files/contest.yaml")
    content = re.sub(r"(?m)^start: .*$", "start: 2026-09-26T10:00:00Z", settings["content"])
    content = re.sub(r"(?m)^end: .*$", "end: 2026-09-26T15:00:00Z", content)
    content = re.sub(r"(?m)^state: .*$", "state: published", content)
    content = re.sub(r"(?m)^visibility: .*$", f"visibility: {visibility}", content)
    written = await client.put(
        f"{CONTEST}/files/contest.yaml",
        json={"encoding": "utf-8", "content": content, "token": settings["token"]},
        headers=ORIGIN,
    )
    assert written.status_code == 200, written.text


async def publish(client: httpx.AsyncClient) -> None:
    """acme/spring/sum published once, by a save of its statement."""
    statement = await read(client, f"{TASK}/files/statement.md")
    saved = await client.put(
        f"{TASK}/files/statement.md",
        json={"encoding": "utf-8", "content": "Add two numbers.\n", "token": statement["token"]},
        headers=ORIGIN,
    )
    assert saved.json()["outcome"] == "published", saved.text


async def edit_task(client: httpx.AsyncClient, old: str, new: str) -> None:
    """acme/spring/sum's `task.yaml` with `old` replaced by `new`, saved,
    confirmed and published by the signed-in organiser.
    """
    current = await read(client, f"{TASK}/files/task.yaml")
    assert old in current["content"]
    saved = await client.put(
        f"{TASK}/files/task.yaml",
        json={
            "encoding": "utf-8",
            "content": current["content"].replace(old, new),
            "token": current["token"],
            "confirm": True,
        },
        headers=ORIGIN,
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["outcome"] == "published", saved.text


async def enter(client: httpx.AsyncClient, forge: FakeForge, setup: Setup, user_id: int) -> None:
    """The user registered for acme/spring through the routes, approved by
    ada and their workspace made, leaving the client signed in as them.
    """
    await sign_in_as(client, forge, user_id)
    registered = await client.post(f"{CONTEST}/registration", json={}, headers=ORIGIN)
    assert registered.status_code == 201, registered.text
    await sign_in_as(client, forge, 7)
    approved = await client.post(f"{CONTEST}/contestants/{user_id}/approve", headers=ORIGIN)
    assert approved.status_code == 200, approved.text
    for _ in range(3):
        await tick(setup, "provisioning")
    await sign_in_as(client, forge, user_id)


@pytest.fixture
async def entered(client: httpx.AsyncClient, world: FakeForge, held_setup: Setup) -> FakeForge:
    """acme/spring public and running, acme/spring/sum published, and carol
    (20) its approved contestant with her workspace made, signed in.
    """
    await run_contest(client, visibility="public")
    await publish(client)
    await enter(client, world, held_setup, 20)
    world.reset_calls()
    return world


async def upload(
    client: httpx.AsyncClient,
    forge: FakeForge,
    content: bytes,
    *,
    input: str = "submission",
    filename: str = "main.py",
) -> dict[str, Any]:
    """A file uploaded the way the browser does: a slot, the bytes posted
    with its form, and the upload completed. Returns the upload.
    """
    slot = await client.post(
        f"{TASK}/uploads",
        json={"input": input, "filename": filename, "size": len(content)},
        headers=ORIGIN,
    )
    assert slot.status_code == 201, slot.text
    forge.objects.post(slot.json()["fields"], content)
    completed = await client.post(
        f"{TASK}/uploads/{slot.json()['id']}/complete", json={}, headers=ORIGIN
    )
    assert completed.status_code == 200, completed.text
    body: dict[str, Any] = completed.json()
    return body
