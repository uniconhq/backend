"""Making a contest makes it before the request answers, and the org lists
it. A name that is taken or breaks the rules is refused. One contest reads
as the list tells it, for an observer at the contest, without its state and
dates while its settings do not read.
"""

import httpx
from forge.api.types import Role
from forge.testing import FakeForge, Setup

from tests.integration.conftest import (
    CONTEST,
    ORG,
    ORIGIN,
    SPRING,
    SUM,
    sign_in,
    sign_in_as,
)

MANAGER_MAY = {
    "manage": True,
    "edit_admin_settings": False,
    "locked_keys": ["name", "description", "state", "visibility", "registration"],
    "see_people": True,
    "manage_people": True,
    "give_admin": False,
}


async def test_a_contest_is_made_and_listed(
    client: httpx.AsyncClient, acme: FakeForge, held_setup: Setup
) -> None:
    await sign_in(client, acme)

    made = await client.post(
        f"{ORG}/contests", json={"name": "spring", "title": "Spring 2026"}, headers=ORIGIN
    )

    assert made.status_code == 201
    assert made.json() == {"name": "spring"}
    assert (await client.get(f"{ORG}/contests")).json() == [
        {
            "name": "spring",
            "state": "draft",
            "start": "2026-10-03T12:00:00Z",
            "end": "2026-10-03T17:00:00Z",
            "may": {
                "manage": True,
                "edit_admin_settings": True,
                "locked_keys": [],
                "see_people": True,
                "manage_people": True,
                "give_admin": True,
            },
        }
    ]
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


async def test_a_contest_only_manager_reads_the_contest_with_a_managers_flags(
    client: httpx.AsyncClient, world: FakeForge
) -> None:
    await world.orgs.grant_role(20, SPRING, Role.MANAGER)
    await sign_in_as(client, world, 20)

    refused = await client.get(f"{ORG}/contests")
    read = await client.get(CONTEST)

    assert refused.status_code == 403
    assert read.status_code == 200
    assert read.json() == {
        "name": "spring",
        "state": "draft",
        "start": "2026-10-03T12:00:00Z",
        "end": "2026-10-03T17:00:00Z",
        "may": MANAGER_MAY,
    }


async def test_a_task_only_holder_is_refused_the_contest(
    client: httpx.AsyncClient, world: FakeForge
) -> None:
    await world.orgs.grant_role(20, SUM, Role.ADMIN)
    await sign_in_as(client, world, 20)

    refused = await client.get(CONTEST)

    assert refused.status_code == 403
    assert refused.json()["code"] == "forbidden"


async def test_a_contest_whose_settings_do_not_read_reads_without_state_or_dates(
    client: httpx.AsyncClient, sum_task: FakeForge
) -> None:
    repo = sum_task.state.repos[("acme", "spring.contest")]
    sum_task.state.commit(repo, {"contest.yaml": b"name: Spring\nstart: not a time\n"}, "Break", 7)

    read = await client.get(CONTEST)

    assert read.status_code == 200
    body = read.json()
    assert (body["name"], body["state"], body["start"], body["end"]) == (
        "spring",
        None,
        None,
        None,
    )
    assert body["may"]["manage"] and body["may"]["edit_admin_settings"]
