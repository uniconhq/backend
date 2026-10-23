"""The one guard in front of every organiser route. Each route is refused to
a caller holding the role just below the one it needs at the scope it names,
with the refusal naming that role and scope, and admitted for a caller
holding exactly that role there. A role held at a broader scope counts, one
held at a narrower scope does not reach up, and a request reads the caller's
roles once. The few reads open to any role at a scope or anything in it are
in a table of their own: a role at the scope or at any narrower one is
admitted, and none there is refused naming the address. Every route under an
org is in one of the two tables but the ones that need only a session, such
as those a contestant calls, and the ones open to a visitor, such as a task's
public files, so a route added there is held to the guard the day it
exists. Every route anywhere that needs no
session at all is in a list of its own, so a route that forgets the session
is caught the day it exists too.
"""

from dataclasses import replace
from typing import Any

import httpx
import pytest
from fastapi.dependencies.models import Dependant
from fastapi.routing import APIRoute
from forge.api import identity
from forge.api.types import Role, Scope
from forge.testing import FakeForge
from starlette.routing import compile_path

from tests.conftest import served_routes
from tests.integration.conftest import (
    ACME,
    CONTEST,
    ORG,
    ORIGIN,
    SPRING,
    SUM,
    TASK,
    sign_in_as,
)
from unicon.api.deps import current_session
from unicon.main import create_app

BELOW = {Role.ADMIN: Role.MANAGER, Role.MANAGER: Role.OBSERVER, Role.OBSERVER: None}
CAROL = {"username": "carol", "role": "observer"}
NEW_FILE = {"encoding": "utf-8", "content": "note\n", "token": None}
ROLLBACK = {"version": "nowhere", "token": None}
NO_GRADING = "0192f4a4-7b7e-7000-8000-000000000001"
NOTE = {"title": "Welcome", "body": "Good luck."}
COMMENT = {"body": "Yes."}
INVITE = {"grants": "observer", "username": "carol"}
NAME = {"name": "Adders"}
MOVE = {"to": "0192f4a4-7b7e-7000-8000-000000000002"}
SECONDS = {"seconds": 60}
ENTRANT = f"{CONTEST}/organise/entrants/{NO_GRADING}"
CANCEL = {"reason": "Not counted."}
MARK = {"value": "review", "mark": "5"}
ASKER = "entrant." + "0" * 31 + "1"
"""An asker as a question names one: an entrant's desk."""
TASK_FILE = {"path": "data/weights.bin", "size": 1, "sha256": "0" * 64}
SESSION_ONLY = {
    "createOrg",
    "getTaskRelease",
    "registerEntrant",
    "getMyEntry",
    "inviteIntoMyEntrant",
    "withdrawMyEntrantsInvite",
    "leaveMyEntrant",
    "renameMyEntrant",
    "getContestHome",
    "getTaskPage",
    "requestUploadSlot",
    "completeUpload",
    "createSubmission",
    "listMySubmissions",
    "getMySubmission",
    "listMySubmissionFiles",
    "readMySubmissionText",
    "listContestAnnouncements",
    "listTaskAnnouncements",
    "askQuestion",
    "listMyQuestions",
    "followUpQuestion",
    "listClarificationInbox",
    "listBoards",
    "getBoard",
    "getMyMarks",
    "markSubmission",
    "unmarkSubmission",
}
OPEN_UNDER_ORGS = {"getTaskPublicFile"}
"""The routes under an org that need no session, since they answer a visitor
what the contest makes public, and a signed-in caller what they may read."""

ROUTES: list[tuple[str, str, dict[str, Any] | None, Role, Scope]] = [
    ("PATCH", ORG, {"description": "Acme"}, Role.ADMIN, ACME),
    ("GET", f"{ORG}/roles", None, Role.OBSERVER, ACME),
    ("POST", f"{ORG}/roles", CAROL, Role.MANAGER, ACME),
    ("DELETE", f"{ORG}/roles/20", None, Role.MANAGER, ACME),
    ("GET", f"{ORG}/contests", None, Role.OBSERVER, ACME),
    ("POST", f"{ORG}/contests", {"name": "autumn"}, Role.MANAGER, ACME),
    ("GET", f"{CONTEST}/roles", None, Role.OBSERVER, SPRING),
    ("POST", f"{CONTEST}/roles", CAROL, Role.MANAGER, SPRING),
    ("DELETE", f"{CONTEST}/roles/20", None, Role.MANAGER, SPRING),
    ("GET", f"{CONTEST}/tasks", None, Role.OBSERVER, SPRING),
    ("POST", f"{CONTEST}/tasks", {"name": "product"}, Role.MANAGER, SPRING),
    ("GET", f"{CONTEST}/organise/entrants", None, Role.OBSERVER, SPRING),
    ("POST", f"{ENTRANT}/approve", None, Role.MANAGER, SPRING),
    ("POST", f"{ENTRANT}/reject", {"reason": "No."}, Role.MANAGER, SPRING),
    ("POST", f"{ENTRANT}/reopen", None, Role.MANAGER, SPRING),
    ("POST", f"{ENTRANT}/remove", None, Role.MANAGER, SPRING),
    ("PUT", f"{ENTRANT}/extension", SECONDS, Role.MANAGER, SPRING),
    ("PUT", f"{ENTRANT}/name", NAME, Role.MANAGER, SPRING),
    ("DELETE", ENTRANT, None, Role.MANAGER, SPRING),
    ("DELETE", f"{ENTRANT}/members/20", None, Role.MANAGER, SPRING),
    ("POST", f"{ENTRANT}/members/20/move", MOVE, Role.MANAGER, SPRING),
    ("GET", f"{CONTEST}/tree", None, Role.OBSERVER, SPRING),
    ("GET", f"{CONTEST}/files/contest.yaml", None, Role.OBSERVER, SPRING),
    ("GET", f"{CONTEST}/history", None, Role.OBSERVER, SPRING),
    ("PUT", f"{CONTEST}/files/notes.md", NEW_FILE, Role.MANAGER, SPRING),
    ("POST", f"{CONTEST}/files/notes.md/rollback", ROLLBACK, Role.MANAGER, SPRING),
    ("GET", f"{CONTEST}/organise/tasks", None, Role.OBSERVER, SPRING),
    ("GET", TASK, None, Role.OBSERVER, SUM),
    ("GET", f"{TASK}/workflow-form", None, Role.OBSERVER, SUM),
    ("GET", f"{TASK}/publications", None, Role.OBSERVER, SUM),
    ("POST", f"{TASK}/save", {"changes": []}, Role.MANAGER, SUM),
    ("POST", f"{TASK}/take-out", {"confirmed": "withdraw"}, Role.MANAGER, SPRING),
    ("POST", f"{TASK}/put-back", None, Role.MANAGER, SPRING),
    ("GET", f"{TASK}/roles", None, Role.OBSERVER, SUM),
    ("POST", f"{TASK}/roles", CAROL, Role.MANAGER, SUM),
    ("DELETE", f"{TASK}/roles/20", None, Role.MANAGER, SUM),
    ("GET", f"{TASK}/tree", None, Role.OBSERVER, SUM),
    ("GET", f"{TASK}/files/task.yaml", None, Role.OBSERVER, SUM),
    ("GET", f"{TASK}/history", None, Role.OBSERVER, SUM),
    ("PUT", f"{TASK}/files/tests/main/1/input", NEW_FILE, Role.MANAGER, SUM),
    ("POST", f"{TASK}/files/task.yaml/rollback", ROLLBACK, Role.MANAGER, SUM),
    ("GET", f"{TASK}/gradings", None, Role.OBSERVER, SUM),
    ("GET", f"{TASK}/gradings/{NO_GRADING}/log", None, Role.OBSERVER, SUM),
    ("GET", f"{TASK}/organise/submissions/1", None, Role.OBSERVER, SUM),
    ("GET", f"{TASK}/organise/submissions/1/texts/out/log", None, Role.OBSERVER, SUM),
    ("POST", f"{TASK}/organise/submissions/1/entries", MARK, Role.MANAGER, SUM),
    ("POST", f"{TASK}/gradings/{NO_GRADING}/cancel", CANCEL, Role.MANAGER, SUM),
    ("POST", f"{TASK}/gradings/{NO_GRADING}/retry", None, Role.MANAGER, SUM),
    ("POST", f"{TASK}/rejudge", None, Role.MANAGER, SUM),
    ("POST", f"{TASK}/results/release", {}, Role.MANAGER, SUM),
    ("GET", f"{CONTEST}/hold", None, Role.OBSERVER, SPRING),
    ("POST", f"{CONTEST}/hold/end", {}, Role.MANAGER, SPRING),
    ("POST", f"{TASK}/results/hide", {}, Role.MANAGER, SUM),
    ("POST", f"{TASK}/regrades/{NO_GRADING}/dismiss", None, Role.MANAGER, SUM),
    ("GET", f"{TASK}/regrades/{NO_GRADING}", None, Role.MANAGER, SUM),
    ("POST", f"{TASK}/organise/uploads", TASK_FILE, Role.MANAGER, SUM),
    ("GET", f"{CONTEST}/announcements", None, Role.OBSERVER, SPRING),
    ("POST", f"{CONTEST}/announcements", NOTE, Role.MANAGER, SPRING),
    ("PATCH", f"{CONTEST}/announcements/1", NOTE, Role.MANAGER, SPRING),
    ("POST", f"{CONTEST}/announcements/1/close", None, Role.MANAGER, SPRING),
    ("POST", f"{CONTEST}/announcements/1/reopen", None, Role.MANAGER, SPRING),
    ("GET", f"{TASK}/announcements", None, Role.OBSERVER, SUM),
    ("POST", f"{TASK}/announcements", NOTE, Role.MANAGER, SUM),
    ("PATCH", f"{TASK}/announcements/1", NOTE, Role.MANAGER, SUM),
    ("POST", f"{TASK}/announcements/1/close", None, Role.MANAGER, SUM),
    ("POST", f"{TASK}/announcements/1/reopen", None, Role.MANAGER, SUM),
    ("GET", f"{CONTEST}/clarifications", None, Role.OBSERVER, SPRING),
    ("POST", f"{CONTEST}/clarifications/{ASKER}/1/replies", COMMENT, Role.MANAGER, SPRING),
    ("PUT", f"{CONTEST}/clarifications/{ASKER}/1/answered", None, Role.MANAGER, SPRING),
    ("DELETE", f"{CONTEST}/clarifications/{ASKER}/1/answered", None, Role.MANAGER, SPRING),
    ("POST", f"{CONTEST}/clarifications/{ASKER}/1/announcement", NOTE, Role.MANAGER, SPRING),
    ("GET", f"{ORG}/invites", None, Role.OBSERVER, ACME),
    ("POST", f"{ORG}/invites", INVITE, Role.MANAGER, ACME),
    ("POST", f"{ORG}/invites/{NO_GRADING}/send-again", None, Role.MANAGER, ACME),
    ("POST", f"{ORG}/invites/{NO_GRADING}/withdraw", None, Role.MANAGER, ACME),
    ("GET", f"{CONTEST}/invites", None, Role.OBSERVER, SPRING),
    ("POST", f"{CONTEST}/invites", INVITE, Role.MANAGER, SPRING),
    ("POST", f"{CONTEST}/invites/{NO_GRADING}/send-again", None, Role.MANAGER, SPRING),
    ("POST", f"{CONTEST}/invites/{NO_GRADING}/withdraw", None, Role.MANAGER, SPRING),
    ("GET", f"{TASK}/invites", None, Role.OBSERVER, SUM),
    ("POST", f"{TASK}/invites", INVITE, Role.MANAGER, SUM),
    ("POST", f"{TASK}/invites/{NO_GRADING}/send-again", None, Role.MANAGER, SUM),
    ("POST", f"{TASK}/invites/{NO_GRADING}/withdraw", None, Role.MANAGER, SUM),
]
ANY_ROLE: list[tuple[str, Scope]] = [
    (ORG, ACME),
    (f"{CONTEST}/gradings", SPRING),
    (f"{CONTEST}/gradings/queue", SPRING),
    (f"{CONTEST}/gradings/regrades", SPRING),
]
"""The reads open to anyone holding a role at the scope or at anything in it,
each a GET."""
INSIDE = {ACME: [ACME, SPRING, SUM], SPRING: [SPRING, SUM]}
EACH_OPEN_ROUTE = pytest.mark.parametrize(
    ("path", "scope"), ANY_ROLE, ids=[path.removeprefix(ORG) or "/" for path, _ in ANY_ROLE]
)
EACH_ROUTE = pytest.mark.parametrize(
    ("method", "path", "body", "role", "scope"),
    ROUTES,
    ids=[f"{method} {path.removeprefix(ORG) or '/'}" for method, path, *_ in ROUTES],
)
SCOPES = pytest.mark.parametrize(
    ("scope", "path"),
    [(ACME, ORG), (SPRING, CONTEST), (SUM, TASK)],
    ids=["org", "contest", "task"],
)


def test_every_route_under_an_org_is_guarded_and_in_the_table() -> None:
    under_orgs = [
        (compile_path(path)[0], route)
        for path, route in served_routes(create_app())
        if path.startswith("/api/v1/orgs")
    ]
    guarded = {route.operation_id for _, route in under_orgs if _is_guarded(route)}
    tables = [(method, path) for method, path, *_ in ROUTES] + [
        ("GET", path) for path, _ in ANY_ROLE
    ]
    listed = {
        route.operation_id
        for method, path in tables
        for pattern, route in under_orgs
        if route.methods == {method} and pattern.fullmatch(path)
    }

    assert len(listed) == len(tables)
    assert guarded == listed
    assert {route.operation_id for _, route in under_orgs} == (
        guarded | SESSION_ONLY | OPEN_UNDER_ORGS
    )


NO_SESSION = {
    "getHealth",
    "getReadiness",
    "getServerTime",
    "startLogin",
    "completeLogin",
    "getRegisterUrl",
    "getForgeUrl",
    "receiveForgeEvent",
    "answerCiConfig",
    "getGradingEnvelope",
    "reportGradingRun",
    "getStepJob",
    "reportStepPipeline",
    "listStepUploads",
    "sayStepDone",
    "getStepFile",
    "listPublicContests",
    "getPublicContest",
    "getPublicStatement",
    "getTaskPublicFile",
    "listPublicBoards",
    "getPublicBoard",
    "listBlocks",
}


def test_every_route_needing_no_session_is_in_the_list() -> None:
    open_routes = {
        route.operation_id
        for _, route in served_routes(create_app())
        if not _needs_session(route.dependant)
    }

    assert open_routes == NO_SESSION


def _needs_session(dependant: Dependant) -> bool:
    return any(
        dependency.call is current_session or _needs_session(dependency)
        for dependency in dependant.dependencies
    )


def _is_guarded(route: APIRoute) -> bool:
    return any(
        (dependency.call.__module__, dependency.call.__name__) == ("unicon.api.guard", "guard")
        for dependency in route.dependant.dependencies
        if dependency.call is not None
    )


async def _as_bob(
    client: httpx.AsyncClient, forge: FakeForge, role: Role | None, scope: Scope
) -> None:
    if role is not None:
        await forge.orgs.grant_role(8, scope, role)
    await sign_in_as(client, forge, 8)


async def _call(
    client: httpx.AsyncClient, method: str, path: str, body: dict[str, Any] | None
) -> httpx.Response:
    return await client.request(method, path, json=body, headers=ORIGIN)


@EACH_ROUTE
async def test_a_caller_just_below_the_role_is_refused_at_the_routes_scope(
    client: httpx.AsyncClient,
    world: FakeForge,
    method: str,
    path: str,
    body: dict[str, Any] | None,
    role: Role,
    scope: Scope,
) -> None:
    await _as_bob(client, world, BELOW[role], scope)

    refused = await _call(client, method, path, body)

    assert refused.status_code == 403, refused.text
    assert refused.json()["code"] == "forbidden"
    assert refused.json()["detail"] == (
        f"This needs the {role.value} role at {scope.name}. Ask an admin of {scope.name} if "
        "you need it."
    )


@EACH_ROUTE
async def test_a_caller_holding_the_role_is_admitted(
    client: httpx.AsyncClient,
    world: FakeForge,
    method: str,
    path: str,
    body: dict[str, Any] | None,
    role: Role,
    scope: Scope,
) -> None:
    await _as_bob(client, world, role, scope)

    admitted = await _call(client, method, path, body)

    assert admitted.status_code not in (401, 403), admitted.text


@EACH_OPEN_ROUTE
async def test_an_open_read_is_refused_to_a_caller_holding_no_role_in_its_scope(
    client: httpx.AsyncClient, world: FakeForge, path: str, scope: Scope
) -> None:
    await _as_bob(client, world, None, scope)

    refused = await client.get(path)

    assert refused.status_code == 403, refused.text
    assert refused.json()["code"] == "forbidden"
    assert refused.json()["detail"] == (
        f"This needs a role at {scope.name} or at something in it. Ask an admin of "
        f"{scope.name} if you need one."
    )


@EACH_OPEN_ROUTE
async def test_an_open_read_admits_a_role_at_its_scope_or_anything_in_it(
    client: httpx.AsyncClient, world: FakeForge, path: str, scope: Scope
) -> None:
    for user_id, inside in enumerate(INSIDE[scope], start=30):
        world.add_user(user_id, f"holder{user_id}")
        await world.orgs.grant_role(user_id, inside, Role.OBSERVER)
        await sign_in_as(client, world, user_id)

        admitted = await client.get(path)

        assert admitted.status_code == 200, (inside, admitted.text)


@EACH_OPEN_ROUTE
async def test_an_open_read_needs_a_session(
    client: httpx.AsyncClient, world: FakeForge, path: str, scope: Scope
) -> None:
    client.cookies.clear()

    refused = await client.get(path)

    assert (refused.status_code, refused.json()["code"]) == (401, "unauthenticated")


@EACH_OPEN_ROUTE
async def test_an_open_read_reads_an_observers_roles_once(
    client: httpx.AsyncClient, world: FakeForge, path: str, scope: Scope
) -> None:
    await _as_bob(client, world, Role.OBSERVER, scope)

    world.reset_calls()
    await client.get(path)

    assert len(world.calls_to("roles_of")) == 1


@SCOPES
async def test_a_higher_role_at_the_org_reaches_every_scope(
    client: httpx.AsyncClient, world: FakeForge, scope: Scope, path: str
) -> None:
    await _as_bob(client, world, Role.ADMIN, ACME)

    granted = await client.post(f"{path}/roles", json=CAROL, headers=ORIGIN)

    assert granted.status_code == 204
    assert 20 in world.state.orgs["acme"].roles[(scope, Role.OBSERVER)]


async def test_a_role_at_a_narrower_scope_does_not_reach_up(
    client: httpx.AsyncClient, world: FakeForge
) -> None:
    await _as_bob(client, world, Role.ADMIN, SUM)

    assert (await client.get(f"{CONTEST}/roles")).status_code == 403
    assert (await client.get(f"{ORG}/roles")).status_code == 403
    assert (await client.get(f"{CONTEST}/tasks/other/roles")).status_code == 403


@SCOPES
async def test_the_roles_are_read_once_per_request(
    client: httpx.AsyncClient, world: FakeForge, scope: Scope, path: str
) -> None:
    await _as_bob(client, world, Role.MANAGER, scope)

    world.reset_calls()
    await client.get(f"{path}/roles")
    assert len(world.calls_to("roles_of")) == 1

    world.reset_calls()
    await client.post(f"{path}/roles", json=CAROL, headers=ORIGIN)
    assert len(world.calls_to("roles_of")) == 1


async def test_a_guarded_route_needs_a_session(client: httpx.AsyncClient) -> None:
    refused = await client.get(f"{ORG}/roles")

    assert refused.status_code == 401
    assert refused.json()["code"] == "unauthenticated"


async def test_an_open_read_is_unavailable_when_the_forge_drops_between_its_reads(
    client: httpx.AsyncClient, world: FakeForge, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A role held only inside the scope is found by reading the person's
    roles again; a forge that drops then gives no roles, which is no
    refusal but the forge not answering."""
    world.add_user(30, "holder30")
    await world.orgs.grant_role(30, Scope("acme", "spring", "sum"), Role.OBSERVER)
    await sign_in_as(client, world, 30)
    whoami = identity.whoami

    async def degraded(session: Any) -> Any:
        found = await whoami(session)
        return replace(found, roles=(), degraded=True)

    monkeypatch.setattr(identity, "whoami", degraded)

    answered = await client.get(f"{CONTEST}/gradings")

    assert (answered.status_code, answered.json()["code"]) == (503, "forge_unavailable")
