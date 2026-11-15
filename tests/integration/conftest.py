"""The app over a real Postgres and the in-memory forge, the way
`UNICON_FORGE=fake` runs it. The test holds forge's setup through
`held_setup`, so the app is served without its lifespan, which would start
forge a second time.

The organiser path starts from `acme`, the org made the operator's way with
ada (7) its admin and the workflow `unicon/classic@v6` public at the fake,
and `sum_task`, the contest acme/spring and the task acme/spring/sum in it
made through the routes and started as a classic task, with ada signed in.
`world` adds carol (20), who holds nothing. `ORG`, `CONTEST` and `TASK` are
the three scopes' URLs, and `ACME`, `SPRING` and `SUM` the scopes
themselves. `run_contest` and `publish` are the two writes a test of a
running contest starts with, `add_task` makes another classic task, and `edit_task`
changes the task's request.
`entered` adds carol alone in an approved entrant of the task's contest, and
`enter` makes anyone else one, answering with the entrant's id; `upload`
sends a file the way the browser does.

The client's machines play each run the fake CI starts: `run_pipelines`
works out what each of its steps writes, from the plan at its publication,
and `end_run` uploads each step's artifact, ends the run and sweeps, so
forge reads it. `publish` and `edit_task` run the save's run alone,
so the publication its check passes takes over and any regrade it starts
waits for the test.
"""

import asyncio
import hashlib
import io
import json
import re
import zipfile
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from datetime import timedelta
from typing import Any
from urllib.parse import parse_qs, urlsplit
from weakref import WeakKeyDictionary

import httpx
import pytest
import yaml
from fastapi import FastAPI
from forge.api import gradings, orgs
from forge.api.types import Scope
from forge.testing import (
    APP_URL,
    FakeClock,
    FakeForge,
    MachineStep,
    RunId,
    Setup,
    machine_steps,
    request_text,
    seed_classic,
    start_classic,
)

from unicon.cli import main
from unicon.main import create_app

ORIGIN = {"Origin": APP_URL}
ORG = "/api/v1/orgs/acme"
CONTEST = f"{ORG}/contests/spring"
TASK = f"{CONTEST}/tasks/sum"
ACME = Scope("acme")
SPRING = Scope("acme", "spring")
SUM = Scope("acme", "spring", "sum")
BUILT_FILES = frozenset({".forgejo/workflows/main.yml", "values.yaml"})
"""The files forge builds from a workflow's request."""

COMPILE_LOG = "SyntaxError: '(' was never closed"
"""The log of a source that does not compile."""
SOLUTION_LOG = "built the solution"
"""The log of an entrant's source that compiles."""
CHECKER_LOG = "built the checker"
"""The log of a source that compiles given a manifest or built at the save:
the classic workflow's compare."""

Command = Callable[[list[str]], Awaitable[int]]


@pytest.fixture(scope="session")
def built_app() -> FastAPI:
    """The app, built once for the process: building it reads no setting and
    keeps nothing of a test, and takes about a second, most of it making the
    OpenAPI document. Its Origin check keeps the public URL it first reads,
    which every test shares.
    """
    return create_app()


@pytest.fixture
def app(held_setup: object, built_app: FastAPI) -> FastAPI:
    return built_app


@dataclass
class Machines:
    """What plays the machines for the runs the test's forge starts: the
    forge, whose CI holds each run, and the setup the plans are read
    through.
    """

    forge: FakeForge
    setup: Setup

    def waiting(self, pipelines: tuple[str, ...]) -> list[RunId]:
        """The runs of the kinds `pipelines` names not yet begun, in the
        order they were started; a save's is the one with no submission."""
        return [
            run
            for run, found in self.forge.ci.runs.items()
            if found.started is None
            and ("grading" if found.dispatch.submission else "save") in pipelines
        ]


MACHINES: WeakKeyDictionary[httpx.AsyncClient, Machines] = WeakKeyDictionary()
"""The machines of each test's client."""


@pytest.fixture
async def client(
    app: FastAPI, fake: FakeForge, held_setup: Setup
) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url=APP_URL) as client:
        MACHINES[client] = Machines(fake, held_setup)
        yield client


Written = dict[str, bytes]
"""What a step's artifact holds: its `outputs.json` and its files, by path."""


async def run_pipelines(
    client: httpx.AsyncClient,
    verdict: str = "accepted",
    pipelines: tuple[str, ...] = ("save", "grading"),
) -> None:
    """Every run of the kinds `pipelines` names started and not yet
    begun, run to its end, and any run that starts in turn. A step
    done once, a build at the save, is accepted; each run of the step that
    compiles the entrant's code ends `verdict`, writing its output, its time
    and its memory when accepted, and every run of it `compile_error` with
    its log when `verdict` is that; each run of a later step, the classic
    workflow's compare, is accepted with a score of 1. A later step does
    only the runs every earlier step accepted, and one left with none is
    skipped, as the step helper skips it.
    """
    machines = MACHINES[client]
    while waiting := machines.waiting(pipelines):
        run = waiting[0]
        await end_run(client, run, await _written(machines, run, verdict))


async def _written(machines: Machines, run: RunId, verdict: str) -> dict[str, Written]:
    """What each step of the run writes to its artifact."""
    written: dict[str, Written] = {}
    accepted: set[str] | None = None
    for step in await machine_steps(machines.setup, machines.forge.ci.runs[run].dispatch.grading):
        if step.runs is None:
            outputs = {"outcome": "accepted", "log": CHECKER_LOG}
            written[step.step] = _outputs({"schema_version": 6, "outputs": outputs})
            continue
        runs = [each for each in step.runs if accepted is None or each in accepted]
        if not runs:
            written[step.step] = {"skipped": b""}
            continue
        files: dict[str, bytes] = {}
        batch: list[dict[str, Any]] = [
            {"run": each, "outputs": _item(step, each, verdict, files)} for each in runs
        ]
        written[step.step] = _outputs({"schema_version": 6, "batch": batch}) | files
        accepted = {entry["run"] for entry in batch if entry["outputs"]["outcome"] == "accepted"}
    return written


def _item(step: MachineStep, run: str, verdict: str, files: dict[str, bytes]) -> dict[str, Any]:
    """One run's outputs, its files added to `files`."""
    if step.compiles and verdict == "compile_error":
        return {"outcome": "compile_error", "log": COMPILE_LOG}
    outcome = verdict if step.compiles else "accepted"
    ran: dict[str, Any] = {
        "outcome": outcome,
        "log": SOLUTION_LOG if step.compiles else CHECKER_LOG,
    }
    if outcome == "accepted":
        ran |= {"output": {"file": f"out/{run}/output"}, "time_ms": 12, "memory_kb": 2048}
        ran |= {} if step.compiles else {"score": 1}
        files[f"out/{run}/output"] = b"3\n"
    return ran


def _outputs(document: object) -> Written:
    return {"outputs.json": json.dumps(document).encode()}


async def end_run(client: httpx.AsyncClient, run: RunId, steps: dict[str, Written]) -> None:
    """The run begun, each step's files uploaded as its artifact, the run
    ended, and the sweep run, which reads it."""
    ci = MACHINES[client].forge.ci
    ci.begin(run)
    for step, files in steps.items():
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, "w") as zipped:
            for path, content in files.items():
                zipped.writestr(path, content)
        # An artifact's name may not hold `/`.
        ci.upload(run, f"out-{step.replace('/', '.')}", archive.getvalue())
    ci.end(run)
    await gradings.sweep()
    await MACHINES[client].setup.settle()


STUCK = timedelta(hours=2)
"""Past every clock a grading waiting for its run keeps."""


async def stuck(client: httpx.AsyncClient, clock: FakeClock) -> None:
    """The clock moved past every clock a grading waits by, and the sweep
    run, with whatever it starts."""
    clock.advance(STUCK)
    await gradings.sweep()
    await MACHINES[client].setup.settle()


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
    """acme, made the operator's way with ada its admin, and the classic
    workflow public at the fake.
    """
    await orgs.create_by_operator("acme", description="Acme", admin_username="ada")
    await seed_classic(forge)
    forge.reset_calls()
    return forge


@pytest.fixture
async def sum_task(client: httpx.AsyncClient, acme: FakeForge, held_setup: Setup) -> FakeForge:
    """acme/spring and acme/spring/sum made through the routes, with ada signed
    in and the task a classic one, not yet saved.
    """
    await sign_in(client, acme)
    made = await client.post(f"{ORG}/contests", json={"name": "spring"}, headers=ORIGIN)
    assert made.status_code == 201, made.text
    made = await client.post(f"{CONTEST}/tasks", json={"name": "sum"}, headers=ORIGIN)
    assert made.status_code == 201, made.text
    await start_classic(acme, "acme/spring/sum", "sum")
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
    A contest opens only once each of its tasks is published with its
    statement written, so a draft's task is published first (`publish`); a
    task not published in a running contest is one made once it is open
    (`add_task`).
    """
    settings = await read(client, f"{CONTEST}/files/contest.yaml")
    if re.search(r"(?m)^state: draft$", settings["content"]):
        await publish(client)
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


async def publish(client: httpx.AsyncClient, task: str = TASK) -> None:
    """acme/spring/sum, or the `task` at that URL, published with its
    statement written, by a save of its statement, confirmed, since a save
    asks first once the contest has started; a task already so, with no
    draft, stays as it is.
    """
    state = (await client.get(task)).json()
    if state["latest"] is not None and state["statement_written"] and not state["draft"]:
        return
    statement = await read(client, f"{task}/files/statement.md")
    saved = await client.put(
        f"{task}/files/statement.md",
        json={
            "encoding": "utf-8",
            "content": "Add two numbers.\n",
            "token": statement["token"],
            "confirm": True,
        },
        headers=ORIGIN,
    )
    saved = await prepared(client, saved, task)
    assert "number" in saved.json(), saved.text
    await run_pipelines(client, pipelines=("save",))


async def add_task(client: httpx.AsyncClient, forge: FakeForge, name: str) -> str:
    """A new unpublished classic task, held at the contest's end until
    scheduled."""
    made = await client.post(f"{CONTEST}/tasks", json={"name": name}, headers=ORIGIN)
    assert made.status_code == 201, made.text
    await start_classic(forge, f"acme/spring/{name}", name)
    return f"{CONTEST}/tasks/{name}"


async def edit_task(client: httpx.AsyncClient, old: str, new: str) -> None:
    """acme/spring/sum's request, as YAML text, with `old` replaced by
    `new`, saved, confirmed and published by the signed-in organiser.
    """
    current = await read(client, f"{TASK}/request")
    text = request_text(current["request"]).decode()
    assert old in text
    saved = await client.post(
        f"{TASK}/save",
        json={
            "request": {
                "request": yaml.safe_load(text.replace(old, new)),
                "token": current["token"],
            },
            "confirm": True,
        },
        headers=ORIGIN,
    )
    assert saved.status_code == 200, saved.text
    saved = await prepared(client, saved)
    assert "number" in saved.json(), saved.text
    await run_pipelines(client, pipelines=("save",))


async def enter(client: httpx.AsyncClient, forge: FakeForge, setup: Setup, user_id: int) -> str:
    """The user registered alone for acme/spring through the routes and
    approved by ada, leaving the client signed in as them; the entrant's id.
    """
    await sign_in_as(client, forge, user_id)
    registered = await client.post(f"{CONTEST}/entrants", json={}, headers=ORIGIN)
    assert registered.status_code == 201, registered.text
    entrant: str = registered.json()["id"]
    await sign_in_as(client, forge, 7)
    approved = await client.post(f"{CONTEST}/organise/entrants/{entrant}/approve", headers=ORIGIN)
    assert approved.status_code == 200, approved.text
    await sign_in_as(client, forge, user_id)
    return entrant


@pytest.fixture
async def entered(client: httpx.AsyncClient, world: FakeForge, held_setup: Setup) -> FakeForge:
    """acme/spring open to everyone and running, acme/spring/sum published, and carol
    (20) its approved contestant, signed in.
    """
    await run_contest(client, visibility="everyone")
    await publish(client)
    await enter(client, world, held_setup, 20)
    world.reset_calls()
    return world


async def entrant_of(client: httpx.AsyncClient) -> str:
    """The id of the entrant the signed-in person is in."""
    panel = await client.get(f"{CONTEST}/entrants/mine")
    assert panel.status_code == 200, panel.text
    entrant: str = panel.json()["entrant"]["id"]
    return entrant


async def upload(
    client: httpx.AsyncClient,
    forge: FakeForge,
    content: bytes,
    *,
    input: str = "code",
    filename: str = "main.py",
    part: int | None = None,
) -> dict[str, Any]:
    """A file uploaded the way the browser does: a slot, the bytes through
    the door, and the upload completed, for one `part` of an input given in
    parts when one is named. Returns the upload.
    """
    slot = await client.post(
        f"{TASK}/uploads",
        json={
            "input": input,
            "filename": filename,
            "size": len(content),
            "sha256": hashlib.sha256(content).hexdigest(),
            "part": part,
        },
        headers=ORIGIN,
    )
    assert slot.status_code == 201, slot.text
    body = slot.json()
    if not body["ready"]:
        door = await client.get(
            "/-/uploads/door",
            headers={
                "X-Original-URI": f"/-/uploads/{body['id']}",
                "X-Upload-Length": str(len(content)),
            },
        )
        assert door.status_code == 204, door.text
        forge.uploads.send(
            door.headers["X-Forge-Path"], door.headers["X-Forge-Authorization"], content
        )
    completed = await client.post(f"{TASK}/uploads/{body['id']}/complete", headers=ORIGIN)
    assert completed.status_code == 200, completed.text
    upload: dict[str, Any] = completed.json()
    return upload


async def prepared(
    client: httpx.AsyncClient, response: httpx.Response, task: str = TASK
) -> httpx.Response:
    """Wait for a fixture's preparation and return its exact publication answer."""
    if not response.is_success or response.json().get("status") != "preparing":
        return response
    await MACHINES[client].setup.settle()
    state = await client.get(f"{task}/preparation")
    assert state.status_code == 200, state.text
    assert state.json()["status"] == "ready", state.text
    return httpx.Response(
        response.status_code, json=state.json()["result"], request=response.request
    )
