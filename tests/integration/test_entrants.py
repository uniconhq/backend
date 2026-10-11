"""Registering an entrant and deciding it, over HTTP. A registration leaves a
pending entrant with the caller its only member, and a refused one answers
with the rule's code; the caller's registration panel shows their entrant,
whether and how they may register, and the reason after a rejection. A
manager lists, approves, rejects, reopens a rejection, removes and extends,
each answer being the entrant as it now stands, and a contestant is refused
every one of those. A refusal of a decision carries its code.
"""

import re

import httpx
from forge.testing import FakeForge, Setup

from tests.integration.conftest import CONTEST, ORIGIN, run_contest, sign_in_as

ENTRANTS = f"{CONTEST}/entrants"
MINE = f"{ENTRANTS}/mine"
ORGANISE = f"{CONTEST}/organise/entrants"


async def _register_carol(
    client: httpx.AsyncClient, world: FakeForge, **body: str
) -> httpx.Response:
    await sign_in_as(client, world, 20)
    return await client.post(ENTRANTS, json=body, headers=ORIGIN)


async def _settings(client: httpx.AsyncClient, world: FakeForge, extra: str) -> None:
    """acme/spring's settings with `extra` added, written as an admin's
    change at the forge would leave it: the contest is running already, and
    a save through the API no longer changes a started contest's entrant
    sizes. ada is signed in afterwards.
    """
    await sign_in_as(client, world, 7)
    repo = world.state.repos[("acme", "spring.contest")]
    content = re.sub(r"(?m)^(registration|entrants):.*\n?", "", repo.files["contest.yaml"].decode())
    world.state.commit(
        repo, {"contest.yaml": (content.rstrip("\n") + "\n" + extra).encode()}, "Settings", 7
    )


async def test_a_registration_is_pending_and_the_caller_reads_it_back(
    client: httpx.AsyncClient, world: FakeForge
) -> None:
    await run_contest(client, visibility="everyone")

    before = await _register_carol(client, world)
    mine = await client.get(MINE)

    assert before.status_code == 201, before.text
    made = before.json()
    assert (made["status"], made["name"], made["display_name"]) == ("pending", None, "carol")
    assert [(member["user_id"], member["way_kind"]) for member in made["members"]] == [
        (20, "signup")
    ]
    assert "email" not in made["members"][0]["user"]
    panel = mine.json()
    assert panel["entrant"] == made
    assert (panel["can_register"], panel["refused"]["code"]) == (False, "already_registered")
    assert (panel["most"], panel["fewest"], panel["locks"]) == (1, 1, "start")


async def test_a_second_registration_answers_with_its_code(
    client: httpx.AsyncClient, world: FakeForge
) -> None:
    await run_contest(client, visibility="everyone")
    await _register_carol(client, world)

    again = await client.post(ENTRANTS, json={}, headers=ORIGIN)

    assert again.status_code == 409
    assert again.json()["code"] == "already_registered"


async def test_an_organiser_registering_is_staff(
    client: httpx.AsyncClient, world: FakeForge
) -> None:
    await run_contest(client, visibility="everyone")

    refused = await client.post(ENTRANTS, json={}, headers=ORIGIN)

    assert refused.status_code == 403
    assert refused.json()["code"] == "is_staff"


async def test_a_contest_the_caller_may_not_see_is_not_found(
    client: httpx.AsyncClient, world: FakeForge
) -> None:
    await run_contest(client, visibility="hidden")

    refused = await _register_carol(client, world)

    assert refused.status_code == 404
    assert refused.json()["code"] == "not_found"


async def test_someone_in_no_entrant_is_told_they_may_register(
    client: httpx.AsyncClient, world: FakeForge
) -> None:
    await run_contest(client, visibility="everyone")
    await sign_in_as(client, world, 20)

    answer = await client.get(MINE)

    assert answer.status_code == 200
    panel = answer.json()
    assert (panel["entrant"], panel["invitations"], panel["refused"]) == (None, [], None)
    assert (panel["can_register"], panel["asks_code"], panel["registration_open"]) == (
        True,
        False,
        True,
    )


async def test_a_code_is_asked_for_only_when_a_code_would_let_the_caller_in(
    client: httpx.AsyncClient, world: FakeForge
) -> None:
    await run_contest(client, visibility="everyone")
    await _settings(
        client, world, "registration:\n  ways: [{signup: {name: Guests, code: sesame}}]\n"
    )
    await sign_in_as(client, world, 20)

    asked = (await client.get(MINE)).json()
    wrong = await client.post(ENTRANTS, json={"code": "open"}, headers=ORIGIN)
    right = await client.post(ENTRANTS, json={"code": "sesame"}, headers=ORIGIN)

    assert (asked["can_register"], asked["asks_code"]) == (True, True)
    assert (wrong.status_code, wrong.json()["code"]) == (403, "wrong_invite_code")
    assert right.status_code == 201, right.text
    assert right.json()["members"][0]["way_name"] == "Guests"


async def test_a_name_is_needed_for_an_entrant_of_several_and_refused_for_one_of_one(
    client: httpx.AsyncClient, world: FakeForge
) -> None:
    await run_contest(client, visibility="everyone")

    alone = await _register_carol(client, world, name="Adders")
    await _settings(client, world, "entrants: {most: 3}\n")
    nameless = await _register_carol(client, world)
    named = await _register_carol(client, world, name="Adders")

    assert (alone.status_code, alone.json()["code"]) == (409, "entrants_alone")
    assert (nameless.status_code, nameless.json()["code"]) == (422, "entrant_name_required")
    assert (named.status_code, named.json()["display_name"]) == (201, "Adders")


async def test_a_manager_decides_and_the_caller_reads_the_reason(
    client: httpx.AsyncClient, world: FakeForge
) -> None:
    await run_contest(client, visibility="everyone")
    entrant = (await _register_carol(client, world)).json()["id"]
    await sign_in_as(client, world, 7)

    listed = await client.get(ORGANISE)
    empty = await client.post(f"{ORGANISE}/{entrant}/reject", json={"reason": " "}, headers=ORIGIN)
    rejected = await client.post(
        f"{ORGANISE}/{entrant}/reject", json={"reason": "Not a student."}, headers=ORIGIN
    )
    approving = await client.post(f"{ORGANISE}/{entrant}/approve", headers=ORIGIN)
    await sign_in_as(client, world, 20)
    mine = (await client.get(MINE)).json()["entrant"]

    [entry] = listed.json()
    assert (entry["display_name"], entry["status"]) == ("carol", "pending")
    assert [(m["user_id"], m["user"]["username"]) for m in entry["members"]] == [(20, "carol")]
    assert "email" in entry["members"][0]["user"]
    assert (empty.status_code, empty.json()["code"]) == (422, "invalid_reason")
    assert rejected.json()["status"] == "rejected"
    assert (approving.status_code, approving.json()["code"]) == (409, "wrong_status")
    assert approving.json()["current"] == "rejected"
    assert (mine["status"], mine["reason"]) == ("rejected", "Not a student.")


async def test_a_rejection_is_taken_back_and_then_approved(
    client: httpx.AsyncClient, world: FakeForge
) -> None:
    await run_contest(client, visibility="everyone")
    entrant = (await _register_carol(client, world)).json()["id"]
    await sign_in_as(client, world, 7)

    pending = await client.post(f"{ORGANISE}/{entrant}/reopen", headers=ORIGIN)
    await client.post(
        f"{ORGANISE}/{entrant}/reject", json={"reason": "Not a student."}, headers=ORIGIN
    )
    reopened = await client.post(f"{ORGANISE}/{entrant}/reopen", headers=ORIGIN)
    approved = await client.post(f"{ORGANISE}/{entrant}/approve", headers=ORIGIN)

    assert (pending.status_code, pending.json()["code"]) == (409, "wrong_status")
    assert (reopened.json()["status"], reopened.json()["reason"]) == ("pending", None)
    assert approved.json()["status"] == "approved"


async def test_an_approved_entrant_is_given_time_and_removed(
    client: httpx.AsyncClient, world: FakeForge, held_setup: Setup
) -> None:
    await run_contest(client, visibility="everyone")
    entrant = (await _register_carol(client, world)).json()["id"]
    await sign_in_as(client, world, 7)
    one = f"{ORGANISE}/{entrant}"

    approved = await client.post(f"{one}/approve", headers=ORIGIN)
    ready = await client.get(ORGANISE)
    extended = await client.put(f"{one}/extension", json={"seconds": 1800}, headers=ORIGIN)
    on_sum = await client.put(
        f"{one}/extension", json={"seconds": 900, "tasks": ["sum"]}, headers=ORIGIN
    )
    unknown = await client.put(
        f"{one}/extension", json={"seconds": 60, "tasks": ["nothing"]}, headers=ORIGIN
    )
    none_named = await client.put(
        f"{one}/extension", json={"seconds": 60, "tasks": []}, headers=ORIGIN
    )
    negative = await client.put(f"{one}/extension", json={"seconds": -1}, headers=ORIGIN)
    huge = await client.put(f"{one}/extension", json={"seconds": 10**20}, headers=ORIGIN)
    removed = await client.post(f"{one}/remove", headers=ORIGIN)

    assert approved.json()["status"] == "approved"
    assert ready.json()[0]["status"] == "approved"
    assert (extended.json()["time_extension"], extended.json()["extension_tasks"]) == (1800, None)
    assert (on_sum.json()["time_extension"], on_sum.json()["extension_tasks"]) == (900, ["sum"])
    for refused in (unknown, none_named, negative):
        assert (refused.status_code, refused.json()["code"]) == (422, "invalid_extension")
    assert (huge.status_code, huge.json()["code"]) == (422, "validation_error")
    assert removed.json()["status"] == "removed"


async def test_an_entrant_that_is_not_there_is_not_found_and_an_id_that_is_not_one_is_refused(
    client: httpx.AsyncClient, world: FakeForge
) -> None:
    await run_contest(client, visibility="everyone")

    missing = await client.post(
        f"{ORGANISE}/0192f4a4-7b7e-7000-8000-000000000001/approve", headers=ORIGIN
    )
    malformed = await client.post(f"{ORGANISE}/not-an-id/approve", headers=ORIGIN)

    assert (missing.status_code, missing.json()["code"]) == (404, "not_found")
    assert (malformed.status_code, malformed.json()["code"]) == (422, "validation_error")


async def test_a_contestant_is_refused_every_decision(
    client: httpx.AsyncClient, world: FakeForge
) -> None:
    await run_contest(client, visibility="everyone")
    entrant = (await _register_carol(client, world)).json()["id"]
    one = f"{ORGANISE}/{entrant}"

    answers = [
        await client.get(ORGANISE),
        await client.post(f"{one}/approve", headers=ORIGIN),
        await client.post(f"{one}/reject", json={"reason": "x"}, headers=ORIGIN),
        await client.post(f"{one}/reopen", headers=ORIGIN),
        await client.post(f"{one}/remove", headers=ORIGIN),
        await client.put(f"{one}/extension", json={"seconds": 1}, headers=ORIGIN),
        await client.put(f"{one}/name", json={"name": "x"}, headers=ORIGIN),
        await client.delete(one, headers=ORIGIN),
        await client.delete(f"{one}/members/20", headers=ORIGIN),
        await client.post(f"{one}/members/20/move", json={"to": entrant}, headers=ORIGIN),
    ]

    assert [(answer.status_code, answer.json()["code"]) for answer in answers] == [
        (403, "forbidden")
    ] * 10


async def test_registering_needs_a_session(client: httpx.AsyncClient, world: FakeForge) -> None:
    client.cookies.clear()

    assert (await client.post(ENTRANTS, json={}, headers=ORIGIN)).status_code == 401
    assert (await client.get(MINE)).status_code == 401
    assert (await client.post(f"{MINE}/leave", headers=ORIGIN)).status_code == 401
