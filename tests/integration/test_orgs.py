"""Creating an org answers at once with its provisioning record, which
carries the org's steps, the status route follows it to ready for the
person who asked and for nobody else, a failed one names the step it stopped
at and when it is tried again, only the org's admin changes what it says
about itself, and a description is at most 255 characters.
"""

import httpx
import pytest
from forge.api.errors import Unavailable
from forge.api.types import Role
from forge.testing import FakeForge, OrgName, Setup, tick

from tests.integration.conftest import ACME, ORG, ORIGIN, sign_in, sign_in_as

PROVISIONING = f"{ORG}/provisioning"
ORG_STEPS = [
    "account_row",
    "org",
    "roles",
    "labels",
    "event_push",
    "first_admin",
    "service_account",
    "service_token",
    "ci_user",
    "ci_login",
]


async def test_creating_an_org_answers_at_once_and_follows_it_to_ready(
    client: httpx.AsyncClient, forge: FakeForge, held_setup: Setup
) -> None:
    await sign_in(client, forge)

    asked = await client.post(
        "/api/v1/orgs", json={"name": "acme", "description": "Acme"}, headers=ORIGIN
    )

    assert asked.status_code == 202
    assert asked.json() == {
        "kind": "org",
        "target": "acme",
        "status": "pending",
        "steps": ORG_STEPS,
        "last_step": None,
        "failed_step": None,
        "error": None,
        "retry_at": None,
        "attempts": 0,
        "ready_at": None,
    }
    assert "acme" not in forge.state.orgs
    following = await client.get(PROVISIONING)
    assert following.status_code == 200
    assert following.json()["status"] == "pending"

    await tick(held_setup, "provisioning")
    done = (await client.get(PROVISIONING)).json()

    assert (done["status"], done["last_step"], done["attempts"], done["error"]) == (
        "ready",
        "ci_login",
        1,
        None,
    )
    assert done["ready_at"] is not None
    me = (await client.get("/api/v1/me")).json()
    assert {
        "scope": {"kind": "org", "org": "acme", "contest": None, "task": None},
        "role": "admin",
    } in me["roles"]


async def test_the_status_of_someone_elses_org_is_not_found(
    client: httpx.AsyncClient, forge: FakeForge
) -> None:
    await sign_in(client, forge)
    await client.post("/api/v1/orgs", json={"name": "acme"}, headers=ORIGIN)
    await sign_in_as(client, forge, 8)

    theirs = await client.get(PROVISIONING)
    nothing = await client.get("/api/v1/orgs/nobody/provisioning")

    assert theirs.status_code == 404
    assert theirs.json()["code"] == "not_found"
    assert nothing.status_code == 404


async def test_a_name_being_made_is_a_conflict(client: httpx.AsyncClient, forge: FakeForge) -> None:
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
    client: httpx.AsyncClient, forge: FakeForge
) -> None:
    await forge.orgs.create_org(OrgName("acme"), description="Acme")
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


async def test_a_manager_may_not_change_the_org(
    client: httpx.AsyncClient, forge: FakeForge
) -> None:
    await forge.orgs.create_org(OrgName("acme"), description="Acme")
    await forge.orgs.grant_role(7, ACME, Role.MANAGER)
    await sign_in(client, forge)

    refused = await client.patch(ORG, json={"description": "Mine now"}, headers=ORIGIN)

    assert refused.status_code == 403
    assert refused.json()["code"] == "forbidden"
    assert forge.state.orgs["acme"].description == "Acme"
    assert forge.calls_to("update_org") == []


async def test_a_failed_org_names_the_step_it_stopped_at_and_when_it_is_tried_again(
    client: httpx.AsyncClient,
    forge: FakeForge,
    held_setup: Setup,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def gone(*args: object, **kwargs: object) -> int:
        raise Unavailable("the CI went away")

    monkeypatch.setattr(forge.grading, "create_ci_user", gone)
    await sign_in(client, forge)
    await client.post("/api/v1/orgs", json={"name": "acme"}, headers=ORIGIN)

    await tick(held_setup, "provisioning")
    failed = (await client.get(PROVISIONING)).json()

    assert (failed["status"], failed["last_step"], failed["failed_step"]) == (
        "failed",
        "service_token",
        "ci_user",
    )
    assert failed["error"] == "the forge or the CI did not answer"
    assert failed["steps"] == ORG_STEPS
    assert failed["retry_at"] is not None


@pytest.mark.parametrize("method", ["post", "patch"])
async def test_a_description_longer_than_255_characters_is_refused(
    client: httpx.AsyncClient, forge: FakeForge, method: str
) -> None:
    await forge.orgs.create_org(OrgName("acme"), description="Acme")
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
    assert kept.status_code in (202, 204)
