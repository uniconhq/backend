"""The app over a real Postgres and the in-memory forge, the way
`UNICON_FORGE=fake` runs it. The test holds forge's setup through
`held_setup`, so the app is served without its lifespan, which would start
forge a second time.

The organiser path starts from `acme`, the org made the operator's way with
ada (7) its admin and the built-in workflow `unicon/classic@v3` public at the
fake as bootstrap makes it, and `sum_task`, the contest acme/spring and the
task acme/spring/sum in it made through the routes, with ada
signed in. `world` adds carol (20), who holds nothing. `ORG`, `CONTEST` and
`TASK` are the three scopes' URLs, and `ACME`, `SPRING` and `SUM` the scopes
themselves. `run_contest` and `publish` are the two writes a test of a
running contest starts with, `add_task` makes another task, and `edit_task`
changes the task's settings.
`entered` adds carol alone in an approved entrant of the task's contest, and
`enter` makes anyone else one, answering with the entrant's id; `upload`
sends a file the way the browser does.

The fake CI asks what each pipeline it starts is while the start is under
way, as the real CI does, and the client's machines keep the answer.
`run_pipelines` then runs each pipeline kept, step by step through the step
doors as the runner's wrapper runs it: its job, what the step wrote put by
the links the door gives and its done said, and the pipeline's report.
`publish` and `edit_task` run the save's pipeline alone, so the publication
its check passes takes over and any regrade it starts waits for the test.
"""

import asyncio
import hashlib
import json
import re
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import parse_qs, urlsplit
from weakref import WeakKeyDictionary

import httpx
import pytest
from fastapi import FastAPI
from forge.api import orgs, runs
from forge.api.types import Scope
from forge.testing import APP_URL, FakeClock, FakeForge, OrgId, Setup, seed_classic

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
    """What runs the pipelines the test's forge starts: the forge, whose
    store takes what a step writes, and each pipeline's steps as the
    platform answered the CI, in the order they were started, until they
    are run.
    """

    forge: FakeForge
    started: list[tuple[str, list[dict[str, Any]]]] = field(default_factory=list)


MACHINES: WeakKeyDictionary[httpx.AsyncClient, Machines] = WeakKeyDictionary()
"""The machines of each test's client."""


@pytest.fixture
async def client(
    app: FastAPI, fake: FakeForge, clock: FakeClock, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url=APP_URL) as client:
        MACHINES[client] = _machines(fake, clock, monkeypatch)
        yield client


def _machines(fake: FakeForge, clock: FakeClock, monkeypatch: pytest.MonkeyPatch) -> Machines:
    """The fake CI asking what each pipeline is as it starts it, and the
    steps it is answered with kept.
    """
    machines = Machines(fake)
    start = fake.grading.start_pipeline

    async def asking(as_: Any, run: Any) -> Any:
        made = await start(as_, run)
        found = fake.ci.runs[made]
        org = OrgId(found.task.split("/", 1)[0])
        answer = await runs.config(
            fake.grading.config_request(org, found.variables, now=clock.now())
        )
        steps = json.loads(answer.body)["steps"]
        machines.started.append((found.variables["UNICON_PIPELINE"], steps))
        return made

    monkeypatch.setattr(fake.grading, "start_pipeline", asking)
    return machines


async def run_pipelines(
    client: httpx.AsyncClient,
    verdict: str = "accepted",
    pipelines: tuple[str, ...] = ("save", "early", "late"),
) -> None:
    """Every pipeline of the kinds `pipelines` names started and not yet
    run, run to its report, and any of them it starts in turn: a compile
    accepted, writing a program; each run of the entrant's program ending
    `verdict`, writing its output, its time and its memory when accepted;
    and each run of a program given a manifest, the classic workflow's
    compare, accepted with a score of 1.
    """
    machines = MACHINES[client]
    while found := [each for each in machines.started if each[0] in pipelines]:
        machines.started.remove(found[0])
        for step in found[0][1]:
            await _run_step(client, machines.forge, step, verdict)


async def _run_step(
    client: httpx.AsyncClient, forge: FakeForge, step: dict[str, Any], verdict: str
) -> None:
    settings = step["settings"]
    door = urlsplit(settings["data_url"]).path
    headers = {"Authorization": f"Bearer {settings['data_token']}"}
    if settings.get("mode") == "report":
        reported = await client.post(door, content=b"{}", headers=headers)
        assert reported.status_code == 200, reported.text
        return
    asked = await client.get(door, headers=headers)
    assert asked.status_code in (200, 204), asked.text
    if asked.status_code == 204:
        return
    written = _written(step["image"], asked.json(), verdict)
    listed = [
        {"path": path, "sha256": hashlib.sha256(content).hexdigest(), "size": len(content)}
        for path, content in written.items()
    ]
    links = await client.post(
        f"{door}/uploads", content=json.dumps({"files": listed}).encode(), headers=headers
    )
    assert links.status_code == 200, links.text
    for path, link in links.json()["files"].items():
        forge.objects.put(link, written[path])
    done = await client.post(f"{door}/done", content=b"{}", headers=headers)
    assert done.status_code == 204, done.text


def _written(image: str, job: dict[str, Any], verdict: str) -> dict[str, bytes]:
    """What a step of `image` writes for `job`: its `outputs.json` and the
    files it names.
    """
    if "/primitive-compile@" in image:
        outputs = {"outcome": "accepted", "log": "", "program": {"file": "out/program"}}
        document: dict[str, Any] = {"schema_version": 6, "outputs": outputs}
        return {"outputs.json": json.dumps(document).encode(), "out/program": b"\x7fELF\n"}
    files: dict[str, bytes] = {}
    batch = []
    for entry in job["inputs"]["batch"]:
        run = entry["run"]
        compare = "manifest" in entry["inputs"]
        ran: dict[str, Any] = {"outcome": "accepted" if compare else verdict}
        if ran["outcome"] == "accepted":
            ran |= {"output": {"file": f"out/{run}/output"}, "time_ms": 12, "memory_kb": 2048}
            ran |= {"score": 1} if compare else {}
            files[f"out/{run}/output"] = b"3\n"
        batch.append({"run": run, "outputs": ran})
    document = {"schema_version": 6, "batch": batch}
    return {"outputs.json": json.dumps(document).encode(), **files}


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
    await orgs.create_by_operator("acme", description="Acme", admin_username="ada")
    await seed_classic(forge)
    forge.reset_calls()
    return forge


@pytest.fixture
async def sum_task(client: httpx.AsyncClient, acme: FakeForge, held_setup: Setup) -> FakeForge:
    """acme/spring and acme/spring/sum made through the routes, with ada signed
    in and the task not yet saved.
    """
    await sign_in(client, acme)
    made = await client.post(f"{ORG}/contests", json={"name": "spring"}, headers=ORIGIN)
    assert made.status_code == 201, made.text
    made = await client.post(f"{CONTEST}/tasks", json={"name": "sum"}, headers=ORIGIN)
    assert made.status_code == 201, made.text
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
    assert "number" in saved.json(), saved.text
    await run_pipelines(client, pipelines=("save",))


async def add_task(client: httpx.AsyncClient, name: str) -> str:
    """Another task of acme/spring made through the routes by the signed-in
    organiser, listed last in the contest, opening with it, and not yet
    published; its URL. In an open contest a new task's entry holds it back
    to the contest's end, so that hold is taken off its entry.
    """
    made = await client.post(f"{CONTEST}/tasks", json={"name": name}, headers=ORIGIN)
    assert made.status_code == 201, made.text
    settings = await read(client, f"{CONTEST}/files/contest.yaml")
    held = rf"(?m)^(\s*- id: {re.escape(name)}\n)\s+release_at: .*\n"
    if re.search(held, settings["content"]):
        written = await client.put(
            f"{CONTEST}/files/contest.yaml",
            json={
                "encoding": "utf-8",
                "content": re.sub(held, r"\1", settings["content"]),
                "token": settings["token"],
            },
            headers=ORIGIN,
        )
        assert written.status_code == 200, written.text
    return f"{CONTEST}/tasks/{name}"


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
