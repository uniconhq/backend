"""Making a workflow needs a session and answers 201 with its owner and name:
under the caller's own username, or under an org where they hold the
manager role or above. An observer of the org, a person with no role there,
an org that is not there and another person's name are refused alike as
`forbidden`; a name that breaks the rules is `invalid_name`, and a name the
owner has already is `conflict`.
"""

import httpx
import pytest
from forge.api.types import Role
from forge.testing import FakeForge

from tests.integration.conftest import ACME, ORIGIN, sign_in, sign_in_as


async def test_a_person_makes_a_workflow_under_their_own_name(
    client: httpx.AsyncClient, acme: FakeForge
) -> None:
    await sign_in_as(client, acme, 8)

    made = await client.post(
        "/api/v1/workflows", json={"owner": "bob", "name": "tuned"}, headers=ORIGIN
    )

    assert made.status_code == 201, made.text
    assert made.json() == {"owner": "bob", "name": "tuned"}
    repo = acme.state.repos[("bob", "tuned.workflow")]
    assert repo.private is True
    assert repo.files["workflow.yaml"].startswith(b"# bob/tuned, a workflow.")


@pytest.mark.parametrize("role", [Role.MANAGER, Role.ADMIN])
async def test_a_manager_or_admin_of_the_org_makes_one_in_the_org(
    client: httpx.AsyncClient, acme: FakeForge, role: Role
) -> None:
    await acme.orgs.grant_role(8, ACME, role)
    await sign_in_as(client, acme, 8)

    made = await client.post(
        "/api/v1/workflows", json={"owner": "acme", "name": "tuned"}, headers=ORIGIN
    )

    assert made.status_code == 201, made.text
    assert made.json() == {"owner": "acme", "name": "tuned"}
    assert ("acme", "tuned.workflow") in acme.state.repos


@pytest.mark.parametrize(
    ("observer", "owner"),
    [(True, "acme"), (False, "acme"), (False, "nowhere"), (False, "ada")],
    ids=["observer", "no role", "no such org", "another person"],
)
async def test_anyone_else_is_refused_alike(
    client: httpx.AsyncClient, acme: FakeForge, observer: bool, owner: str
) -> None:
    if observer:
        await acme.orgs.grant_role(8, ACME, Role.OBSERVER)
    await sign_in_as(client, acme, 8)

    refused = await client.post(
        "/api/v1/workflows", json={"owner": owner, "name": "tuned"}, headers=ORIGIN
    )

    assert refused.status_code == 403
    assert refused.json()["code"] == "forbidden"
    assert refused.json()["detail"] == f"This needs the manager role at {owner}."
    assert acme.calls_to("create_workflow") == []


async def test_a_name_that_breaks_the_rules_is_invalid(
    client: httpx.AsyncClient, acme: FakeForge
) -> None:
    await sign_in(client, acme)

    refused = await client.post(
        "/api/v1/workflows", json={"owner": "ada", "name": "Tuned!"}, headers=ORIGIN
    )

    assert refused.status_code == 422
    assert refused.json()["code"] == "invalid_name"


async def test_a_name_the_owner_has_already_is_a_conflict(
    client: httpx.AsyncClient, acme: FakeForge
) -> None:
    await sign_in(client, acme)
    body = {"owner": "acme", "name": "tuned"}
    first = await client.post("/api/v1/workflows", json=body, headers=ORIGIN)
    assert first.status_code == 201, first.text

    again = await client.post("/api/v1/workflows", json=body, headers=ORIGIN)

    assert again.status_code == 409
    assert again.json()["code"] == "conflict"


async def test_making_a_workflow_needs_a_session(client: httpx.AsyncClient) -> None:
    refused = await client.post(
        "/api/v1/workflows", json={"owner": "ada", "name": "tuned"}, headers=ORIGIN
    )

    assert refused.status_code == 401
    assert refused.json()["code"] == "unauthenticated"


async def test_making_a_workflow_needs_the_apps_origin(
    client: httpx.AsyncClient, acme: FakeForge
) -> None:
    await sign_in(client, acme)

    refused = await client.post(
        "/api/v1/workflows",
        json={"owner": "ada", "name": "tuned"},
        headers={"Origin": "http://elsewhere.test"},
    )

    assert refused.status_code == 403
    assert refused.json()["code"] == "origin_mismatch"
    assert acme.calls_to("create_workflow") == []
