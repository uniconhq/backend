"""Making a contest makes it before the request answers, and the org lists
it. A name that is taken or breaks the rules is refused.
"""

import httpx
from forge.testing import FakeForge, Setup

from tests.integration.conftest import CONTEST, ORG, ORIGIN, sign_in


async def test_a_contest_is_made_and_listed(
    client: httpx.AsyncClient, acme: FakeForge, held_setup: Setup
) -> None:
    await sign_in(client, acme)

    made = await client.post(
        f"{ORG}/contests", json={"name": "spring", "title": "Spring 2026"}, headers=ORIGIN
    )

    assert made.status_code == 201
    assert made.json() == {"name": "spring"}
    assert (await client.get(f"{ORG}/contests")).json() == [{"name": "spring"}]
    settings = (await client.get(f"{CONTEST}/files/contest.yaml")).json()
    assert 'name: "Spring 2026"' in settings["content"]


async def test_a_name_taken_is_a_conflict(client: httpx.AsyncClient, acme: FakeForge) -> None:
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
