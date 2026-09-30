"""The one guard in front of every organiser route. Each route is refused to
a caller holding the role just below the one it needs at the scope it names,
with the refusal naming that role and scope, and admitted for a caller
holding exactly that role there. A role held at a broader scope counts, one
held at a narrower scope does not reach up, and a request reads the caller's
roles once. Every route under an org is in the table below but the ones that
need only a session, such as those a contestant calls, so a route added there
is held to the guard the day it exists. Every route anywhere that needs no
session at all is in a list of its own, so a route that forgets the session
is caught the day it exists too.
"""

from typing import Any

import httpx
import pytest
from fastapi.dependencies.models import Dependant
from fastapi.routing import APIRoute
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
SESSION_ONLY = {
    "createOrg",
    "getOrgProvisioning",
    "getTaskRelease",
    "registerForContest",
    "getMyRegistration",
    "getContestHome",
    "getTaskPage",
    "requestUploadSlot",
    "completeUpload",
    "createSubmission",
    "listMySubmissions",
    "getMySubmission",
    "listMySubmissionFiles",
    "readMySubmissionFile",
    "readMySubmissionLog",
}

ROUTES: list[tuple[str, str, dict[str, Any] | None, Role, Scope]] = [
    ("PATCH", ORG, {"description": "Acme"}, Role.ADMIN, ACME),
    ("GET", f"{ORG}/roles", None, Role.OBSERVER, ACME),
    ("POST", f"{ORG}/roles", CAROL, Role.MANAGER, ACME),
    ("DELETE", f"{ORG}/roles/20", None, Role.MANAGER, ACME),
    ("GET", f"{ORG}/contests", None, Role.OBSERVER, ACME),
    ("POST", f"{ORG}/contests", {"name": "autumn"}, Role.MANAGER, ACME),
    ("GET", f"{CONTEST}/provisioning", None, Role.OBSERVER, ACME),
    ("GET", f"{CONTEST}/roles", None, Role.OBSERVER, SPRING),
    ("POST", f"{CONTEST}/roles", CAROL, Role.MANAGER, SPRING),
    ("DELETE", f"{CONTEST}/roles/20", None, Role.MANAGER, SPRING),
    ("GET", f"{CONTEST}/tasks", None, Role.OBSERVER, SPRING),
    ("POST", f"{CONTEST}/tasks", {"name": "product"}, Role.MANAGER, SPRING),
    ("GET", f"{TASK}/provisioning", None, Role.OBSERVER, SPRING),
    ("GET", f"{CONTEST}/contestants", None, Role.OBSERVER, SPRING),
    ("POST", f"{CONTEST}/contestants/20/approve", None, Role.MANAGER, SPRING),
    ("POST", f"{CONTEST}/contestants/20/reject", {"reason": "No."}, Role.MANAGER, SPRING),
    ("POST", f"{CONTEST}/contestants/20/remove", None, Role.MANAGER, SPRING),
    ("PUT", f"{CONTEST}/contestants/20/extension", {"seconds": 60}, Role.MANAGER, SPRING),
    ("GET", f"{CONTEST}/tree", None, Role.OBSERVER, SPRING),
    ("GET", f"{CONTEST}/files/contest.yaml", None, Role.OBSERVER, SPRING),
    ("GET", f"{CONTEST}/history", None, Role.OBSERVER, SPRING),
    ("PUT", f"{CONTEST}/files/notes.md", NEW_FILE, Role.MANAGER, SPRING),
    ("POST", f"{CONTEST}/files/notes.md/rollback", ROLLBACK, Role.MANAGER, SPRING),
    ("GET", TASK, None, Role.OBSERVER, SUM),
    ("GET", f"{TASK}/publications", None, Role.OBSERVER, SUM),
    ("POST", f"{TASK}/save", {"changes": []}, Role.MANAGER, SUM),
    ("GET", f"{TASK}/roles", None, Role.OBSERVER, SUM),
    ("POST", f"{TASK}/roles", CAROL, Role.MANAGER, SUM),
    ("DELETE", f"{TASK}/roles/20", None, Role.MANAGER, SUM),
    ("GET", f"{TASK}/tree", None, Role.OBSERVER, SUM),
    ("GET", f"{TASK}/files/task.yaml", None, Role.OBSERVER, SUM),
    ("GET", f"{TASK}/history", None, Role.OBSERVER, SUM),
    ("PUT", f"{TASK}/files/data/testcases/1.in", NEW_FILE, Role.MANAGER, SUM),
    ("POST", f"{TASK}/files/task.yaml/rollback", ROLLBACK, Role.MANAGER, SUM),
    ("POST", f"{TASK}/gradings/{NO_GRADING}/cancel", None, Role.MANAGER, SUM),
    ("POST", f"{TASK}/gradings/{NO_GRADING}/retry", None, Role.MANAGER, SUM),
    ("POST", f"{TASK}/rejudge", None, Role.MANAGER, SUM),
]
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
    listed = {
        route.operation_id
        for method, path, *_ in ROUTES
        for pattern, route in under_orgs
        if route.methods == {method} and pattern.fullmatch(path)
    }

    assert len(listed) == len(ROUTES)
    assert guarded == listed
    assert {route.operation_id for _, route in under_orgs} == guarded | SESSION_ONLY


NO_SESSION = {
    "getHealth",
    "getReadiness",
    "getServerTime",
    "startLogin",
    "completeLogin",
    "getRegisterUrl",
    "receiveForgeEvent",
    "answerCiConfig",
    "getGradingEnvelope",
    "reportGradingRun",
    "listPublicContests",
    "getPublicContest",
    "getPublicStatement",
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
    assert refused.json()["detail"] == f"This needs the {role.value} role at {scope.name}."


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
