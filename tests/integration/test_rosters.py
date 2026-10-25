"""The routes of who is in an entrant: a member invites someone in, who joins
by accepting the invite, both submit as the entrant, and one leaves; an
organiser lists, renames, moves and takes out members, deletes an entrant
and gives one more time. Forge's refusals come back with their codes, and a
contestant cannot reach the organisers' routes.
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
    publish,
    run_contest,
    sign_in_as,
    upload,
)

ENTRANTS = f"{CONTEST}/entrants"
MINE = f"{ENTRANTS}/mine"
ORGANISE = f"{CONTEST}/organise/entrants"


async def _entrants_of(
    client: httpx.AsyncClient,
    forge: FakeForge,
    most: int = 2,
    *,
    ways: str = "[{invite: {}}, {signup: {approval: auto}}]",
) -> None:
    """acme/spring taking entrants of up to `most`, their rosters locking at
    their first submission, by `ways`, written as an admin's change at the
    forge would leave it: the contest is running already, and a save through
    the API no longer moves a started contest from everyone alone to teams.
    ada is signed in afterwards.
    """
    await sign_in_as(client, forge, 7)
    repo = forge.state.repos[("acme", "spring.contest")]
    content = re.sub(r"(?m)^(registration|entrants):.*\n?", "", repo.files["contest.yaml"].decode())
    content = content.rstrip("\n") + (
        f"\nregistration: {{ways: {ways}}}\nentrants: {{most: {most}, locks: first_submission}}\n"
    )
    forge.state.commit(repo, {"contest.yaml": content.encode()}, "Settings", 7)


async def _submit(client: httpx.AsyncClient, forge: FakeForge, key: str) -> httpx.Response:
    made = await upload(client, forge, f"print({key!r})\n".encode())
    return await client.post(
        f"{TASK}/submissions",
        json={
            "inputs": {
                "code": {"uploads": [made["id"]]},
                "language": {"value": "python"},
            },
            "idempotency_key": key,
        },
        headers=ORIGIN,
    )


async def _join(client: httpx.AsyncClient, forge: FakeForge, user_id: int) -> httpx.Response:
    """The user accepts the one invite waiting for them."""
    await sign_in_as(client, forge, user_id)
    [waiting] = (await client.get("/api/v1/me/invites")).json()
    return await client.post(f"/api/v1/me/invites/{waiting['id']}/accept", headers=ORIGIN)


async def test_an_entrant_forms_by_invite_and_submits_as_one(
    client: httpx.AsyncClient, world: FakeForge, held_setup: Setup, clock: FakeClock
) -> None:
    await run_contest(client, visibility="everyone")
    await publish(client)
    world.add_user(21, "dan")
    await _entrants_of(client, world)

    await sign_in_as(client, world, 20)
    made = await client.post(ENTRANTS, json={"name": "Adders"}, headers=ORIGIN)
    assert made.status_code == 201, made.text
    adders = made.json()
    assert (adders["name"], adders["status"], [m["user_id"] for m in adders["members"]]) == (
        "Adders",
        "approved",
        [20],
    )
    asked = await client.post(f"{MINE}/invites", json={"username": "dan"}, headers=ORIGIN)
    assert asked.status_code == 201, asked.text
    assert (asked.json()["grants"], asked.json()["entrant"]) == (
        "member",
        {"id": adders["id"], "name": "Adders"},
    )

    await sign_in_as(client, world, 21)
    panel = (await client.get(MINE)).json()
    assert [each["entrant"]["name"] for each in panel["invitations"]] == ["Adders"]
    joined = await _join(client, world, 21)
    assert joined.status_code == 200, joined.text
    assert joined.json()["invite"]["status"] == "accepted"
    assert joined.json()["entered"] == {
        "entrant": {"id": adders["id"], "name": "Adders"},
        "status": "approved",
        "how": "joined",
    }

    await sign_in_as(client, world, 20)
    assert (await _submit(client, world, "key-0001-aaaa")).status_code == 201
    clock.advance(timedelta(seconds=31))
    await sign_in_as(client, world, 21)
    assert (await _submit(client, world, "key-0002-bbbb")).json()["number"] == 2
    mine = (await client.get(MINE)).json()["entrant"]
    assert sorted(m["user_id"] for m in mine["members"]) == [20, 21]
    assert mine["locked"] is True
    assert [made["number"] for made in (await client.get(f"{TASK}/submissions")).json()] == [2, 1]

    locked = await client.post(f"{MINE}/leave", headers=ORIGIN)
    assert (locked.status_code, locked.json()["code"]) == (403, "roster_locked")


async def test_a_member_leaves_before_the_roster_locks_and_withdraws_an_invite(
    client: httpx.AsyncClient, entered: FakeForge, held_setup: Setup
) -> None:
    entered.add_user(21, "dan")
    await _entrants_of(client, entered)
    await sign_in_as(client, entered, 20)
    asked = await client.post(f"{MINE}/invites", json={"username": "dan"}, headers=ORIGIN)
    renamed = await client.put(f"{MINE}/name", json={"name": "Adders"}, headers=ORIGIN)

    withdrawn = await client.delete(f"{MINE}/invites/{asked.json()['id']}", headers=ORIGIN)
    left = await client.post(f"{MINE}/leave", headers=ORIGIN)

    assert renamed.json()["display_name"] == "Adders"
    assert withdrawn.json()["status"] == "withdrawn"
    assert left.status_code == 204
    assert (await client.get(MINE)).json()["entrant"] is None


async def test_the_refusals_come_back_with_their_codes(
    client: httpx.AsyncClient, entered: FakeForge, held_setup: Setup
) -> None:
    entered.add_user(21, "dan")
    entered.add_user(22, "erin")
    await sign_in_as(client, entered, 20)
    alone = await client.post(f"{MINE}/invites", json={"username": "dan"}, headers=ORIGIN)
    assert (alone.status_code, alone.json()["code"]) == (409, "entrants_alone")
    await _entrants_of(client, entered, most=2)

    await sign_in_as(client, entered, 20)
    await client.put(f"{MINE}/name", json={"name": "Adders"}, headers=ORIGIN)
    await client.post(f"{MINE}/invites", json={"username": "dan"}, headers=ORIGIN)
    twice = await client.post(f"{MINE}/invites", json={"username": "dan"}, headers=ORIGIN)
    full = await client.post(f"{MINE}/invites", json={"username": "erin"}, headers=ORIGIN)
    staff = await client.post(f"{MINE}/invites", json={"username": "ada"}, headers=ORIGIN)

    assert (twice.status_code, twice.json()["code"]) == (409, "already_invited")
    assert (full.status_code, full.json()["code"], full.json()["limit"]) == (
        409,
        "entrant_full",
        2,
    )
    assert (staff.status_code, staff.json()["code"]) == (403, "is_staff")

    await sign_in_as(client, entered, 22)
    taken = await client.post(ENTRANTS, json={"name": "adders"}, headers=ORIGIN)
    outside = await client.post(f"{MINE}/leave", headers=ORIGIN)
    assert (taken.status_code, taken.json()["code"]) == (409, "entrant_name_taken")
    assert (outside.status_code, outside.json()["code"]) == (404, "not_found")
    assert (await client.get(ORGANISE)).status_code == 403


async def test_an_organiser_lists_renames_moves_takes_out_and_deletes(
    client: httpx.AsyncClient, entered: FakeForge, held_setup: Setup
) -> None:
    entered.add_user(21, "dan")
    await enter(client, entered, held_setup, 21)
    await _entrants_of(client, entered)

    listed = (await client.get(ORGANISE)).json()
    carols, dans = (entry["id"] for entry in listed)
    renamed = await client.put(f"{ORGANISE}/{carols}/name", json={"name": "Adders"}, headers=ORIGIN)
    moved = await client.post(
        f"{ORGANISE}/{dans}/members/21/move", json={"to": carols}, headers=ORIGIN
    )
    out = await client.delete(f"{ORGANISE}/{carols}/members/21", headers=ORIGIN)
    gone = await client.delete(f"{ORGANISE}/{carols}", headers=ORIGIN)

    assert [entry["display_name"] for entry in listed] == ["carol", "dan"]
    assert renamed.json()["name"] == "Adders"
    assert moved.status_code == 200, moved.text
    assert [(m["user_id"], m["way_kind"]) for m in moved.json()["members"]] == [
        (20, "signup"),
        (21, "organiser"),
    ]
    assert [m["user_id"] for m in out.json()["members"]] == [20]
    assert gone.status_code == 204
    assert (await client.get(ORGANISE)).json() == []


async def test_an_organiser_puts_someone_straight_into_an_entrant_by_invite(
    client: httpx.AsyncClient, entered: FakeForge, held_setup: Setup
) -> None:
    entered.add_user(21, "dan")
    await _entrants_of(client, entered)
    [carols] = (await client.get(ORGANISE)).json()

    made = await client.post(
        f"{CONTEST}/invites",
        json={"grants": "contestant", "username": "dan", "entrant": carols["id"]},
        headers=ORIGIN,
    )
    joined = await _join(client, entered, 21)

    assert made.status_code == 201, made.text
    assert made.json()["entrant"] == {"id": carols["id"], "name": "carol"}
    assert joined.json()["entered"]["how"] == "joined"
    member = (await client.get(MINE)).json()["entrant"]["members"][1]
    assert (member["user_id"], member["way_kind"]) == (21, "organiser")


async def test_an_organiser_gives_an_entrant_more_time_on_a_task(
    client: httpx.AsyncClient, entered: FakeForge, held_setup: Setup
) -> None:
    await sign_in_as(client, entered, 7)
    [entrant] = (await client.get(ORGANISE)).json()
    one = f"{ORGANISE}/{entrant['id']}"

    extended = await client.put(
        f"{one}/extension", json={"seconds": 3600, "tasks": ["sum"]}, headers=ORIGIN
    )
    unknown = await client.put(
        f"{one}/extension", json={"seconds": 3600, "tasks": ["nothing"]}, headers=ORIGIN
    )
    await sign_in_as(client, entered, 20)
    home = await client.get(f"{CONTEST}/home")
    refused = await client.put(f"{one}/extension", json={"seconds": 60}, headers=ORIGIN)

    assert extended.status_code == 200, extended.text
    assert (extended.json()["time_extension"], extended.json()["extension_tasks"]) == (
        3600,
        ["sum"],
    )
    assert (unknown.status_code, unknown.json()["code"]) == (422, "invalid_extension")
    assert home.json()["tasks"][0]["closes"] == "2026-09-26T16:00:00Z"
    assert (refused.status_code, refused.json()["code"]) == (403, "forbidden")
