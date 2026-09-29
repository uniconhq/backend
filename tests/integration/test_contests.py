"""Making a contest answers at once with its provisioning record, the poller
makes it, the status route follows it to ready, and the org lists it. A
name that is taken or breaks the rules is refused.
"""

import httpx
from forge.testing import FakeForge, Setup, tick

from tests.integration.conftest import CONTEST, ORG, ORIGIN, sign_in


async def test_a_contest_is_asked_for_made_by_the_poller_and_listed(
    client: httpx.AsyncClient, acme: FakeForge, held_setup: Setup
) -> None:
    await sign_in(client, acme)

    asked = await client.post(
        f"{ORG}/contests", json={"name": "spring", "title": "Spring 2026"}, headers=ORIGIN
    )

    assert asked.status_code == 202
    assert (asked.json()["kind"], asked.json()["target"], asked.json()["status"]) == (
        "contest",
        "acme/spring",
        "pending",
    )
    assert (await client.get(f"{CONTEST}/provisioning")).json()["status"] == "pending"
    assert (await client.get(f"{ORG}/contests")).json() == []

    await tick(held_setup, "provisioning")

    done = (await client.get(f"{CONTEST}/provisioning")).json()
    assert (done["status"], done["last_step"], done["error"]) == ("ready", "roles", None)
    assert (await client.get(f"{ORG}/contests")).json() == [{"name": "spring"}]
    settings = (await client.get(f"{CONTEST}/files/contest.yaml")).json()
    assert 'name: "Spring 2026"' in settings["content"]


async def test_a_contest_nothing_asked_for_is_not_found(
    client: httpx.AsyncClient, acme: FakeForge
) -> None:
    await sign_in(client, acme)

    missing = await client.get(f"{ORG}/contests/autumn/provisioning")

    assert missing.status_code == 404
    assert missing.json()["code"] == "not_found"


async def test_a_name_being_made_is_a_conflict(client: httpx.AsyncClient, acme: FakeForge) -> None:
    await sign_in(client, acme)
    await client.post(f"{ORG}/contests", json={"name": "spring"}, headers=ORIGIN)

    again = await client.post(f"{ORG}/contests", json={"name": "spring"}, headers=ORIGIN)

    assert again.status_code == 409
    assert again.json()["code"] == "conflict"


async def test_a_name_that_breaks_the_rules_is_refused(
    client: httpx.AsyncClient, acme: FakeForge
) -> None:
    await sign_in(client, acme)

    refused = await client.post(f"{ORG}/contests", json={"name": "Spring 2026"}, headers=ORIGIN)

    assert refused.status_code == 422
    assert refused.json()["code"] == "invalid_name"
