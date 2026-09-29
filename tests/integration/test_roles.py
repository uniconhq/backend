"""The role routes list the holders at a scope with where each holds it,
grant, move and remove holders, and pass forge's three refusals through
with their codes: a manager granting admin, the last admin leaving, and a
contestant of the contest being given a role.
"""

import httpx
from forge.api.types import ContestId, Role, Scope
from forge.testing import FakeForge, Setup, register_contestant

from tests.integration.conftest import (
    ACME,
    CONTEST,
    ORG,
    ORIGIN,
    SPRING,
    SUM,
    TASK,
    sign_in,
    sign_in_as,
)

ORG_ROLES = f"{ORG}/roles"
CONTEST_ROLES = f"{CONTEST}/roles"
TASK_ROLES = f"{TASK}/roles"


def _held(forge: FakeForge, user_id: int) -> set[tuple[Scope, Role]]:
    return {held for held, members in forge.state.orgs["acme"].roles.items() if user_id in members}


async def test_the_holders_at_a_task_say_where_each_holds_their_role(
    client: httpx.AsyncClient, world: FakeForge
) -> None:
    await world.orgs.grant_role(8, SPRING, Role.MANAGER)
    await world.orgs.grant_role(20, SUM, Role.OBSERVER)
    await sign_in(client, world)

    listed = await client.get(TASK_ROLES)

    assert listed.status_code == 200
    assert listed.json() == [
        {
            "user_id": 7,
            "username": "ada",
            "name": "Ada Lovelace",
            "avatar_url": None,
            "role": "admin",
            "scope": {"kind": "org", "org": "acme", "contest": None, "task": None},
            "inherited": True,
        },
        {
            "user_id": 8,
            "username": "bob",
            "name": None,
            "avatar_url": None,
            "role": "manager",
            "scope": {"kind": "contest", "org": "acme", "contest": "spring", "task": None},
            "inherited": True,
        },
        {
            "user_id": 20,
            "username": "carol",
            "name": "Carol",
            "avatar_url": "http://forge.test/avatars/carol",
            "role": "observer",
            "scope": {"kind": "task", "org": "acme", "contest": "spring", "task": "sum"},
            "inherited": False,
        },
    ]


async def test_an_admin_grants_moves_and_removes_a_holder(
    client: httpx.AsyncClient, world: FakeForge
) -> None:
    await sign_in(client, world)

    granted = await client.post(
        CONTEST_ROLES, json={"username": "carol", "role": "observer"}, headers=ORIGIN
    )
    assert granted.status_code == 204
    assert _held(world, 20) == {(SPRING, Role.OBSERVER)}

    promoted = await client.post(
        CONTEST_ROLES, json={"username": "carol", "role": "admin"}, headers=ORIGIN
    )
    assert promoted.status_code == 204
    assert _held(world, 20) == {(SPRING, Role.ADMIN)}

    removed = await client.delete(f"{CONTEST_ROLES}/20", headers=ORIGIN)
    assert removed.status_code == 204
    assert _held(world, 20) == set()


async def test_a_manager_granting_admin_is_refused(
    client: httpx.AsyncClient, world: FakeForge
) -> None:
    await world.orgs.grant_role(8, SPRING, Role.MANAGER)
    await sign_in_as(client, world, 8)

    refused = await client.post(
        CONTEST_ROLES, json={"username": "carol", "role": "admin"}, headers=ORIGIN
    )

    assert refused.status_code == 403
    assert refused.json()["code"] == "forbidden"
    assert refused.json()["detail"] == "Only an admin of acme/spring may grant admin there."
    assert _held(world, 20) == set()


async def test_removing_the_last_admin_is_refused_naming_the_scope(
    client: httpx.AsyncClient, world: FakeForge
) -> None:
    await sign_in(client, world)

    refused = await client.delete(f"{ORG_ROLES}/7", headers=ORIGIN)

    assert refused.status_code == 409
    assert refused.json()["code"] == "sole_admin"
    assert refused.json()["scopes"] == [{"kind": "org", "name": "acme"}]
    assert _held(world, 7) == {(ACME, Role.ADMIN)}


async def test_a_contestant_is_given_no_role_in_their_contest(
    client: httpx.AsyncClient, world: FakeForge, held_setup: Setup
) -> None:
    await register_contestant(held_setup, ContestId("acme/spring"), 8)
    await sign_in(client, world)

    refused = await client.post(
        TASK_ROLES, json={"username": "bob", "role": "observer"}, headers=ORIGIN
    )

    assert refused.status_code == 409
    assert refused.json()["code"] == "contestant_conflict"
    assert refused.json()["contests"] == ["acme/spring"]
    assert _held(world, 8) == set()


async def test_a_user_the_forge_does_not_know_is_not_found(
    client: httpx.AsyncClient, world: FakeForge
) -> None:
    await sign_in(client, world)

    refused = await client.post(
        ORG_ROLES, json={"username": "nobody", "role": "observer"}, headers=ORIGIN
    )

    assert refused.status_code == 404
    assert refused.json()["code"] == "not_found"


async def test_a_role_that_does_not_exist_is_a_validation_error(
    client: httpx.AsyncClient, world: FakeForge
) -> None:
    await sign_in(client, world)

    refused = await client.post(
        ORG_ROLES, json={"username": "carol", "role": "owner"}, headers=ORIGIN
    )

    assert refused.status_code == 422
    assert refused.json()["code"] == "validation_error"
