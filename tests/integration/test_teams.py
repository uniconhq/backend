"""The team routes: a contestant makes a team and another joins it once the
leader lets them in, both submit as the team, and an organiser lists and
mends the contest's teams and gives one more time. Forge's refusals come
back with their codes, and a contestant cannot reach the organisers'
routes.
"""

import re
from datetime import timedelta

import httpx
from forge.testing import FakeClock, FakeForge, Setup

from tests.integration.conftest import (
    CONTEST,
    ORIGIN,
    TASK,
    enter,
    sign_in_as,
    upload,
)

TEAMS = f"{CONTEST}/teams"
ORGANISE = f"{CONTEST}/organise/teams"


async def _teams_on(client: httpx.AsyncClient, forge: FakeForge, size: int = 2) -> None:
    await sign_in_as(client, forge, 7)
    settings = (await client.get(f"{CONTEST}/files/contest.yaml")).json()
    content = re.sub(r"(?m)^team_size: .*\n?", "", settings["content"]).rstrip("\n")
    content += f"\nteam_size: {size}\n"
    written = await client.put(
        f"{CONTEST}/files/contest.yaml",
        json={"encoding": "utf-8", "content": content, "token": settings["token"]},
        headers=ORIGIN,
    )
    assert written.status_code == 200, written.text


async def _submit(client: httpx.AsyncClient, forge: FakeForge, key: str) -> httpx.Response:
    made = await upload(client, forge, f"print({key!r})\n".encode())
    return await client.post(
        f"{TASK}/submissions",
        json={
            "inputs": {
                "submission": {"uploads": [made["id"]]},
                "language": {"value": "python"},
            },
            "idempotency_key": key,
        },
        headers=ORIGIN,
    )


async def test_a_team_forms_and_submits_as_one(
    client: httpx.AsyncClient, entered: FakeForge, held_setup: Setup, clock: FakeClock
) -> None:
    entered.add_user(21, "dan")
    await enter(client, entered, held_setup, 21)
    await _teams_on(client, entered)

    await sign_in_as(client, entered, 20)
    made = await client.post(TEAMS, json={"name": "Adders"}, headers=ORIGIN)
    assert made.status_code == 201, made.text
    team = made.json()
    assert (team["name"], team["leader"], [m["user_id"] for m in team["members"]]) == (
        "Adders",
        20,
        [20],
    )

    await sign_in_as(client, entered, 21)
    listed = (await client.get(TEAMS)).json()
    assert [(t["name"], t["size"], t["max_size"]) for t in listed] == [("Adders", 1, 2)]
    asked = await client.post(f"{TEAMS}/{team['id']}/request", headers=ORIGIN)
    assert asked.status_code == 200, asked.text
    assert (await client.get(f"{CONTEST}/my-team")).json()["requested"][0]["name"] == "Adders"

    await sign_in_as(client, entered, 20)
    let_in = await client.post(f"{TEAMS}/{team['id']}/members/21/approve", headers=ORIGIN)
    assert let_in.status_code == 200, let_in.text
    assert (await _submit(client, entered, "key-0001-aaaa")).status_code == 201
    clock.advance(timedelta(seconds=31))

    await sign_in_as(client, entered, 21)
    assert (await _submit(client, entered, "key-0002-bbbb")).json()["number"] == 2
    mine = (await client.get(f"{CONTEST}/my-team")).json()
    assert mine["team"]["name"] == "Adders"
    assert [made["number"] for made in (await client.get(f"{TASK}/submissions")).json()] == [2, 1]

    left = await client.post(f"{CONTEST}/my-team/leave", headers=ORIGIN)
    assert left.status_code == 204
    assert (await client.get(f"{CONTEST}/my-team")).json()["team"] is None


async def test_the_refusals_come_back_with_their_codes(
    client: httpx.AsyncClient, entered: FakeForge, held_setup: Setup
) -> None:
    entered.add_user(21, "dan")
    entered.add_user(22, "erin")
    await enter(client, entered, held_setup, 21)
    refused = await client.post(TEAMS, json={"name": "Early"}, headers=ORIGIN)
    assert (refused.status_code, refused.json()["code"]) == (409, "teams_off")
    await enter(client, entered, held_setup, 22)
    await _teams_on(client, entered, size=2)

    await sign_in_as(client, entered, 20)
    team = (await client.post(TEAMS, json={"name": "Adders"}, headers=ORIGIN)).json()
    await client.post(f"{TEAMS}/{team['id']}/invite", json={"username": "dan"}, headers=ORIGIN)
    await sign_in_as(client, entered, 21)
    joined = await client.post(f"{TEAMS}/{team['id']}/request", headers=ORIGIN)
    assert joined.status_code == 200, joined.text
    await sign_in_as(client, entered, 20)
    full = await client.post(
        f"{TEAMS}/{team['id']}/invite", json={"username": "erin"}, headers=ORIGIN
    )
    assert (full.status_code, full.json()["code"], full.json()["limit"]) == (409, "team_full", 2)

    await sign_in_as(client, entered, 22)
    taken = await client.post(TEAMS, json={"name": "adders"}, headers=ORIGIN)
    assert (taken.status_code, taken.json()["code"]) == (409, "team_name_taken")
    not_leader = await client.delete(f"{TEAMS}/{team['id']}/members/20", headers=ORIGIN)
    assert (not_leader.status_code, not_leader.json()["code"]) == (403, "forbidden")
    assert (await client.get(ORGANISE)).status_code == 403


async def test_an_organiser_lists_and_mends_teams(
    client: httpx.AsyncClient, entered: FakeForge, held_setup: Setup
) -> None:
    await _teams_on(client, entered)
    made = await client.post(ORGANISE, json={"name": "Mended", "leader": "carol"}, headers=ORIGIN)
    assert made.status_code == 201, made.text
    team = made.json()
    empty = (await client.post(ORGANISE, json={"name": "Spare"}, headers=ORIGIN)).json()

    moved = await client.post(
        f"{ORGANISE}/{empty['id']}/members", json={"user_id": 20}, headers=ORIGIN
    )
    assert [m["user_id"] for m in moved.json()["members"]] == [20]
    assert [t["name"] for t in (await client.get(ORGANISE)).json()] == ["Spare"]
    assert team["id"] != empty["id"]
    gone = await client.delete(f"{ORGANISE}/{empty['id']}/members/20", headers=ORIGIN)
    assert gone.status_code == 200
    assert (await client.get(ORGANISE)).json() == []


async def test_an_organiser_gives_a_team_more_time_on_a_task(
    client: httpx.AsyncClient, entered: FakeForge, held_setup: Setup
) -> None:
    await _teams_on(client, entered)
    team = (
        await client.post(ORGANISE, json={"name": "Late", "leader": "carol"}, headers=ORIGIN)
    ).json()

    extended = await client.put(
        f"{ORGANISE}/{team['id']}/extension",
        json={"seconds": 3600, "tasks": ["sum"]},
        headers=ORIGIN,
    )
    unknown = await client.put(
        f"{ORGANISE}/{team['id']}/extension",
        json={"seconds": 3600, "tasks": ["nothing"]},
        headers=ORIGIN,
    )
    await sign_in_as(client, entered, 20)
    home = await client.get(f"{CONTEST}/home")
    refused = await client.put(
        f"{ORGANISE}/{team['id']}/extension", json={"seconds": 60}, headers=ORIGIN
    )

    assert extended.status_code == 200, extended.text
    assert (extended.json()["time_extension"], extended.json()["extension_tasks"]) == (
        3600,
        ["sum"],
    )
    assert (unknown.status_code, unknown.json()["code"]) == (422, "invalid_extension")
    assert home.json()["tasks"][0]["closes"] == "2026-09-26T16:00:00Z"
    assert (refused.status_code, refused.json()["code"]) == (403, "forbidden")
