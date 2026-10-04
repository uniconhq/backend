"""The account routes: identity with roles, the session list, and the two ways
to leave with the package's refusals passed through.
"""

from datetime import timedelta

import httpx
from fastapi import FastAPI
from forge.api.types import Role, Scope
from forge.testing import AsUser, FakeClock, FakeForge, OrgId, Setup, Visibility, name_places

from tests.integration.conftest import ORIGIN, sign_in
from unicon.api.cookies import SESSION_COOKIE


async def test_me_lists_roles_at_every_scope(
    client: httpx.AsyncClient, forge: FakeForge, held_setup: Setup
) -> None:
    await forge.orgs.create_org(OrgId("acme"), description="Acme")
    await name_places(held_setup, "acme", "acme/spring", "acme/spring/sum")
    await forge.orgs.grant_role(7, Scope("acme"), Role.ADMIN)
    await forge.orgs.grant_role(7, Scope("acme", "spring", "sum"), Role.OBSERVER)
    await sign_in(client, forge)

    me = await client.get("/api/v1/me")

    assert me.json()["roles"] == [
        {"names": {"org": "acme", "contest": None, "task": None}, "role": "admin"},
        {
            "names": {"org": "acme", "contest": "spring", "task": "sum"},
            "role": "observer",
        },
    ]


async def test_a_forge_that_is_down_degrades_me(
    client: httpx.AsyncClient, forge: FakeForge
) -> None:
    await sign_in(client, forge)
    forge.unavailable = True

    me = await client.get("/api/v1/me")

    assert me.status_code == 200
    assert me.json()["user"]["username"] == "ada"
    assert me.json()["degraded"] is True


async def test_a_second_browser_shows_and_is_revoked_from_the_first(
    client: httpx.AsyncClient, forge: FakeForge, app: FastAPI
) -> None:
    await sign_in(client, forge)
    other = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://app.test")
    async with other:
        await sign_in(other, forge)

        listed = (await client.get("/api/v1/me/sessions")).json()
        assert len(listed) == 2
        stranger = next(entry for entry in listed if not entry["current"])

        gone = await client.delete(f"/api/v1/me/sessions/{stranger['id']}", headers=ORIGIN)
        assert gone.status_code == 204
        assert (await other.get("/api/v1/me")).status_code == 401
        assert (await client.get("/api/v1/me")).status_code == 200


async def test_sign_out_everywhere_ends_this_session_too(
    client: httpx.AsyncClient, forge: FakeForge
) -> None:
    await sign_in(client, forge)

    gone = await client.delete("/api/v1/me/sessions", headers=ORIGIN)

    assert gone.status_code == 204
    assert SESSION_COOKIE not in client.cookies


async def test_deactivating_needs_a_fresh_sign_in(
    client: httpx.AsyncClient, forge: FakeForge, clock: FakeClock
) -> None:
    await sign_in(client, forge)
    clock.advance(timedelta(minutes=6))

    refused = await client.post("/api/v1/me/deactivate", headers=ORIGIN)

    assert refused.status_code == 403
    assert refused.json()["code"] == "fresh_sign_in_required"
    assert forge.users[7].active is True


async def test_deactivating_signs_out_and_turns_the_account_off(
    client: httpx.AsyncClient, forge: FakeForge
) -> None:
    await sign_in(client, forge)

    done = await client.post("/api/v1/me/deactivate", headers=ORIGIN)

    assert done.status_code == 204
    assert forge.users[7].active is False
    assert (await client.get("/api/v1/me")).status_code == 401


async def test_a_delete_refusal_names_the_scopes(
    client: httpx.AsyncClient, forge: FakeForge, held_setup: Setup
) -> None:
    await forge.orgs.create_org(OrgId("acme"), description="Acme")
    await name_places(held_setup, "acme")
    await forge.orgs.grant_role(7, Scope("acme"), Role.ADMIN)
    await sign_in(client, forge)

    refused = await client.delete("/api/v1/me", headers=ORIGIN)

    assert refused.status_code == 409
    assert refused.json()["code"] == "sole_admin"
    assert refused.json()["scopes"] == [{"kind": "org", "name": "acme"}]
    assert 7 in forge.users


async def test_a_delete_refusal_names_the_shared_workflow(
    client: httpx.AsyncClient, forge: FakeForge
) -> None:
    ada = AsUser(7, forge.mint(7))
    workflow = await forge.workflows.create_workflow(ada, "ada", "classic", {}, Visibility.PRIVATE)
    await forge.workflows.share_workflow(ada, workflow, 8)
    await sign_in(client, forge)

    refused = await client.delete("/api/v1/me", headers=ORIGIN)

    assert refused.json()["code"] == "shared_workflow_owner"
    assert refused.json()["workflows"] == ["ada/classic"]


async def test_a_delete_removes_the_account(client: httpx.AsyncClient, forge: FakeForge) -> None:
    await sign_in(client, forge)

    gone = await client.delete("/api/v1/me", headers=ORIGIN)

    assert gone.status_code == 204
    assert 7 not in forge.users
    assert (await client.get("/api/v1/me")).status_code == 401
