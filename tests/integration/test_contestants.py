"""Registering for a contest and deciding the registrations, over HTTP. A
registration leaves a pending row and a refused one answers with the rule's
code; the caller's own registration shows the reason after a rejection. A
manager lists, approves, rejects, removes and extends, each answer being the
row as it now stands, and a contestant is refused every one of those. A
refusal of a decision carries its code.
"""

import httpx
from forge.testing import FakeForge, Setup, tick

from tests.integration.conftest import CONTEST, ORIGIN, run_contest, sign_in_as

REGISTRATION = f"{CONTEST}/registration"
CONTESTANTS = f"{CONTEST}/contestants"


async def _register_carol(client: httpx.AsyncClient, world: FakeForge) -> httpx.Response:
    await sign_in_as(client, world, 20)
    return await client.post(REGISTRATION, json={}, headers=ORIGIN)


async def test_a_registration_is_pending_and_the_caller_reads_it_back(
    client: httpx.AsyncClient, world: FakeForge
) -> None:
    await run_contest(client, visibility="public")

    before = await _register_carol(client, world)
    mine = await client.get(REGISTRATION)

    assert before.status_code == 201, before.text
    assert before.json()["status"] == "pending"
    assert before.json()["workspace"] is None
    assert mine.json() == before.json()


async def test_a_second_registration_answers_with_its_code(
    client: httpx.AsyncClient, world: FakeForge
) -> None:
    await run_contest(client, visibility="public")
    await _register_carol(client, world)

    again = await client.post(REGISTRATION, json={}, headers=ORIGIN)

    assert again.status_code == 409
    assert again.json()["code"] == "already_registered"


async def test_an_organiser_registering_is_staff(
    client: httpx.AsyncClient, world: FakeForge
) -> None:
    await run_contest(client, visibility="public")

    refused = await client.post(REGISTRATION, json={}, headers=ORIGIN)

    assert refused.status_code == 403
    assert refused.json()["code"] == "is_staff"


async def test_a_contest_the_caller_may_not_see_is_not_found(
    client: httpx.AsyncClient, world: FakeForge
) -> None:
    await run_contest(client, visibility="hidden")

    refused = await _register_carol(client, world)

    assert refused.status_code == 404
    assert refused.json()["code"] == "not_found"


async def test_no_registration_reads_as_null(client: httpx.AsyncClient, world: FakeForge) -> None:
    await sign_in_as(client, world, 20)

    answer = await client.get(REGISTRATION)

    assert answer.status_code == 200
    assert answer.json() is None


async def test_a_manager_decides_and_the_caller_reads_the_reason(
    client: httpx.AsyncClient, world: FakeForge
) -> None:
    await run_contest(client, visibility="public")
    await _register_carol(client, world)
    await sign_in_as(client, world, 7)

    listed = await client.get(CONTESTANTS)
    empty = await client.post(f"{CONTESTANTS}/20/reject", json={"reason": " "}, headers=ORIGIN)
    rejected = await client.post(
        f"{CONTESTANTS}/20/reject", json={"reason": "Not a student."}, headers=ORIGIN
    )
    approving = await client.post(f"{CONTESTANTS}/20/approve", headers=ORIGIN)
    await sign_in_as(client, world, 20)
    mine = await client.get(REGISTRATION)

    assert [(entry["user_id"], entry["username"], entry["status"]) for entry in listed.json()] == [
        (20, "carol", "pending")
    ]
    assert (empty.status_code, empty.json()["code"]) == (422, "invalid_reason")
    assert rejected.json()["status"] == "rejected"
    assert (approving.status_code, approving.json()["code"]) == (409, "wrong_status")
    assert approving.json()["current"] == "rejected"
    assert (mine.json()["status"], mine.json()["reason"]) == ("rejected", "Not a student.")


async def test_an_approved_contestant_is_given_time_and_removed(
    client: httpx.AsyncClient, world: FakeForge, held_setup: Setup
) -> None:
    await run_contest(client, visibility="public")
    await _register_carol(client, world)
    await sign_in_as(client, world, 7)

    approved = await client.post(f"{CONTESTANTS}/20/approve", headers=ORIGIN)
    await tick(held_setup, "provisioning")
    ready = await client.get(CONTESTANTS)
    extended = await client.put(
        f"{CONTESTANTS}/20/extension", json={"seconds": 1800}, headers=ORIGIN
    )
    negative = await client.put(f"{CONTESTANTS}/20/extension", json={"seconds": -1}, headers=ORIGIN)
    huge = await client.put(f"{CONTESTANTS}/20/extension", json={"seconds": 10**20}, headers=ORIGIN)
    removed = await client.post(f"{CONTESTANTS}/20/remove", headers=ORIGIN)

    assert (approved.json()["status"], approved.json()["workspace"]) == ("approved", "preparing")
    assert ready.json()[0]["workspace"] == "ready"
    assert extended.json()["time_extension_seconds"] == 1800
    assert (negative.status_code, negative.json()["code"]) == (422, "invalid_extension")
    assert (huge.status_code, huge.json()["code"]) == (422, "validation_error")
    assert (removed.json()["status"], removed.json()["workspace"]) == ("removed", None)
    assert 20 not in world.state.repos[("acme", "spring.carol.desk")].writers


async def test_a_contestant_is_refused_every_decision(
    client: httpx.AsyncClient, world: FakeForge
) -> None:
    await run_contest(client, visibility="public")
    await _register_carol(client, world)

    answers = [
        await client.get(CONTESTANTS),
        await client.post(f"{CONTESTANTS}/20/approve", headers=ORIGIN),
        await client.post(f"{CONTESTANTS}/20/reject", json={"reason": "x"}, headers=ORIGIN),
        await client.post(f"{CONTESTANTS}/20/remove", headers=ORIGIN),
        await client.put(f"{CONTESTANTS}/20/extension", json={"seconds": 1}, headers=ORIGIN),
    ]

    assert [(answer.status_code, answer.json()["code"]) for answer in answers] == [
        (403, "forbidden")
    ] * 5


async def test_registering_needs_a_session(client: httpx.AsyncClient, world: FakeForge) -> None:
    client.cookies.clear()

    assert (await client.post(REGISTRATION, json={}, headers=ORIGIN)).status_code == 401
    assert (await client.get(REGISTRATION)).status_code == 401
