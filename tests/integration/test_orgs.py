"""Creating an org makes it before the request answers, with the caller its
admin, a failure answers with the forge's refusal and leaves the name free,
anyone holding a role in the org, at it or at anything in it, reads what
it says about itself and only its admin changes it, and a description is at most 255 characters.
"""

import httpx
import pytest
from forge.api.errors import Unavailable
from forge.api.types import Role, Scope
from forge.testing import FakeForge, OrgId, Setup, name_places

from tests.integration.conftest import ACME, ORG, ORIGIN, sign_in


async def test_creating_an_org_makes_it_with_the_caller_its_admin(
    client: httpx.AsyncClient, forge: FakeForge, held_setup: Setup
) -> None:
    await sign_in(client, forge)

    made = await client.post(
        "/api/v1/orgs", json={"name": "acme", "description": "Acme"}, headers=ORIGIN
    )

    assert made.status_code == 201
    assert made.json() == {"name": "acme"}
    assert "acme" in forge.state.orgs
    me = (await client.get("/api/v1/me")).json()
    assert {
        "names": {"org": "acme", "contest": None, "task": None},
        "role": "admin",
    } in me["roles"]


async def test_a_name_taken_is_a_conflict(client: httpx.AsyncClient, forge: FakeForge) -> None:
    await sign_in(client, forge)
    await client.post("/api/v1/orgs", json={"name": "acme"}, headers=ORIGIN)

    again = await client.post("/api/v1/orgs", json={"name": "acme"}, headers=ORIGIN)

    assert again.status_code == 409
    assert again.json()["code"] == "conflict"


async def test_a_name_forge_refuses_is_invalid(client: httpx.AsyncClient, forge: FakeForge) -> None:
    await sign_in(client, forge)

    refused = await client.post("/api/v1/orgs", json={"name": "Acme!"}, headers=ORIGIN)

    assert refused.status_code == 422
    assert refused.json()["code"] == "invalid_name"


async def test_creating_needs_a_session(client: httpx.AsyncClient) -> None:
    refused = await client.post("/api/v1/orgs", json={"name": "acme"}, headers=ORIGIN)

    assert refused.status_code == 401
    assert refused.json()["code"] == "unauthenticated"


async def test_an_admin_changes_the_orgs_description(
    client: httpx.AsyncClient, forge: FakeForge, held_setup: Setup
) -> None:
    await forge.orgs.create_org(OrgId("acme"), description="Acme")
    await name_places(held_setup, "acme")
    await forge.orgs.grant_role(7, ACME, Role.ADMIN)
    await sign_in(client, forge)

    changed = await client.patch(
        ORG,
        json={"description": "Acme contests", "display_name": "Acme Inc."},
        headers=ORIGIN,
    )

    assert changed.status_code == 204
    org = forge.state.orgs["acme"]
    assert (org.description, org.display_name) == ("Acme contests", "Acme Inc.")
    read = await client.get(ORG)
    assert read.status_code == 200, read.text
    assert read.json() == {"display_name": "Acme Inc.", "description": "Acme contests"}


async def test_an_observer_of_the_org_reads_what_it_says_about_itself(
    client: httpx.AsyncClient, forge: FakeForge, held_setup: Setup
) -> None:
    await forge.orgs.create_org(OrgId("acme"), description="Acme")
    await name_places(held_setup, "acme")
    await forge.orgs.grant_role(7, ACME, Role.OBSERVER)
    await sign_in(client, forge)

    read = await client.get(ORG)

    assert read.status_code == 200, read.text
    assert read.json() == {"display_name": None, "description": "Acme"}
    assert forge.calls_to("update_org") == []


async def test_a_role_anywhere_in_the_org_reads_what_it_says_and_none_reads_nothing(
    client: httpx.AsyncClient, forge: FakeForge, held_setup: Setup
) -> None:
    await forge.orgs.create_org(OrgId("acme"), description="Acme")
    await forge.orgs.create_org(OrgId("globex"), description="Globex")
    await name_places(held_setup, "acme", "acme/spring", "globex")
    await forge.orgs.grant_role(7, Scope("acme", "spring"), Role.ADMIN)
    await sign_in(client, forge)

    admitted = await client.get(ORG)
    refused = await client.get("/api/v1/orgs/globex")
    client.cookies.clear()
    anonymous = await client.get(ORG)

    assert admitted.status_code == 200, admitted.text
    assert admitted.json()["description"] == "Acme"
    assert (refused.status_code, refused.json()["code"]) == (403, "forbidden")
    assert (anonymous.status_code, anonymous.json()["code"]) == (401, "unauthenticated")


async def test_a_manager_may_not_change_the_org(
    client: httpx.AsyncClient, forge: FakeForge, held_setup: Setup
) -> None:
    await forge.orgs.create_org(OrgId("acme"), description="Acme")
    await name_places(held_setup, "acme")
    await forge.orgs.grant_role(7, ACME, Role.MANAGER)
    await sign_in(client, forge)

    refused = await client.patch(ORG, json={"description": "Mine now"}, headers=ORIGIN)

    assert refused.status_code == 403
    assert refused.json()["code"] == "forbidden"
    assert forge.state.orgs["acme"].description == "Acme"
    assert forge.calls_to("update_org") == []


async def test_a_failed_org_answers_with_the_refusal_and_leaves_the_name_free(
    client: httpx.AsyncClient,
    forge: FakeForge,
    held_setup: Setup,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def gone(*args: object, **kwargs: object) -> object:
        raise Unavailable("the CI went away")

    monkeypatch.setattr(forge.grading, "set_up_org", gone)
    await sign_in(client, forge)

    failed = await client.post("/api/v1/orgs", json={"name": "acme"}, headers=ORIGIN)

    assert failed.status_code == 503
    assert failed.json()["code"] == "forge_unavailable"
    assert "the CI went away" not in failed.text
    me = (await client.get("/api/v1/me")).json()
    assert all(held["names"]["org"] != "acme" for held in me["roles"])


@pytest.mark.parametrize("method", ["post", "patch"])
async def test_a_description_longer_than_255_characters_is_refused(
    client: httpx.AsyncClient, forge: FakeForge, method: str, held_setup: Setup
) -> None:
    await forge.orgs.create_org(OrgId("acme"), description="Acme")
    await name_places(held_setup, "acme")
    await forge.orgs.grant_role(7, ACME, Role.ADMIN)
    await sign_in(client, forge)
    url, body = ("/api/v1/orgs", {"name": "other"}) if method == "post" else (ORG, {})

    refused = await client.request(
        method.upper(), url, json={**body, "description": "x" * 256}, headers=ORIGIN
    )
    kept = await client.request(
        method.upper(), url, json={**body, "description": "x" * 255}, headers=ORIGIN
    )

    assert refused.status_code == 422
    assert refused.json()["code"] == "validation_error"
    assert kept.status_code in (201, 204)
