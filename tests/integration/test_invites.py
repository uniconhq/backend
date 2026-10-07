"""The invite routes: an organiser makes, lists, sends again and withdraws a
scope's invites; the person they are for lists, opens, accepts and declines
their own, and nobody else can. Forge's refusals come back with their codes,
a lapsed invite and a manager inviting an admin among them.
"""

from dataclasses import replace
from datetime import timedelta

import httpx
from forge.api.types import Role
from forge.testing import FakeClock, FakeForge, Setup

from tests.integration.conftest import (
    CONTEST,
    ORG,
    ORIGIN,
    SPRING,
    TASK,
    run_contest,
    sign_in,
    sign_in_as,
)

CONTEST_INVITES = f"{CONTEST}/invites"


def _token(forge: FakeForge) -> str:
    return forge.mail.sent[-1].text.split("/invites#", 1)[1].split()[0]


async def test_an_organiser_invites_by_username_and_the_person_accepts_the_role(
    client: httpx.AsyncClient, world: FakeForge, held_setup: Setup
) -> None:
    world.state.users[20] = replace(world.state.users[20], email="carol@example.test")
    made = await client.post(
        CONTEST_INVITES, json={"grants": "observer", "username": "carol"}, headers=ORIGIN
    )
    assert made.status_code == 201, made.text
    invite = made.json()
    assert invite["where"] == {"org": "acme", "contest": "spring", "task": None}
    assert (invite["grants"], invite["username"], invite["status"]) == (
        "observer",
        "carol",
        "pending",
    )
    assert invite["invited_by"]["username"] == "ada"
    await held_setup.settle()
    listed = await client.get(CONTEST_INVITES)
    assert [(found["id"], found["mail_status"]) for found in listed.json()] == [
        (invite["id"], "sent")
    ]

    await sign_in_as(client, world, 20)
    mine = await client.get("/api/v1/me/invites")
    assert [found["id"] for found in mine.json()] == [invite["id"]]
    opened = await client.post(
        "/api/v1/me/invites/open", json={"token": _token(world)}, headers=ORIGIN
    )
    assert opened.json()["id"] == invite["id"]
    accepted = await client.post(f"/api/v1/me/invites/{invite['id']}/accept", headers=ORIGIN)

    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["status"] == "accepted"
    assert 20 in world.state.orgs["acme"].roles[(SPRING, Role.OBSERVER)]


async def test_nobody_else_lists_opens_accepts_or_declines_someone_elses_invite(
    client: httpx.AsyncClient, world: FakeForge, held_setup: Setup
) -> None:
    made = await client.post(
        CONTEST_INVITES, json={"grants": "manager", "email": "dan@uni.test"}, headers=ORIGIN
    )
    invite = made.json()
    await held_setup.settle()

    await sign_in_as(client, world, 20)
    assert (await client.get("/api/v1/me/invites")).json() == []
    for action in ("accept", "decline"):
        refused = await client.post(f"/api/v1/me/invites/{invite['id']}/{action}", headers=ORIGIN)
        assert (refused.status_code, refused.json()["code"]) == (404, "not_found")
    opened = await client.post(
        "/api/v1/me/invites/open", json={"token": _token(world)}, headers=ORIGIN
    )
    assert (opened.status_code, opened.json()["code"]) == (404, "not_found")
    # carol holds no role here, so the organiser's list is closed to her too.
    assert (await client.get(CONTEST_INVITES)).status_code == 403


async def test_an_email_invite_lets_its_person_register_for_an_invite_only_contest(
    client: httpx.AsyncClient, world: FakeForge, held_setup: Setup
) -> None:
    await run_contest(client, visibility="everyone")
    settings = await client.get(f"{CONTEST}/files/contest.yaml")
    content = settings.json()["content"].replace(
        "visibility: everyone", "visibility: everyone\nregistration: {invite_only: true}"
    )
    assert "invite_only: true" in content
    written = await client.put(
        f"{CONTEST}/files/contest.yaml",
        json={"encoding": "utf-8", "content": content, "token": settings.json()["token"]},
        headers=ORIGIN,
    )
    assert written.status_code == 200, written.text
    made = await client.post(
        CONTEST_INVITES, json={"grants": "contestant", "email": "Dan@Uni.test"}, headers=ORIGIN
    )
    assert made.status_code == 201, made.text

    world.add_user(21, "dan", email="dan@uni.test")
    await sign_in_as(client, world, 21)
    refused = await client.post(f"{CONTEST}/registration", json={}, headers=ORIGIN)
    assert refused.json()["code"] == "invite_required"
    [waiting] = (await client.get("/api/v1/me/invites")).json()
    await client.post(f"/api/v1/me/invites/{waiting['id']}/accept", headers=ORIGIN)
    registered = await client.post(f"{CONTEST}/registration", json={}, headers=ORIGIN)

    assert registered.status_code == 201, registered.text


async def test_the_refusals_come_back_with_their_codes(
    client: httpx.AsyncClient, world: FakeForge, clock: FakeClock
) -> None:
    await world.orgs.grant_role(20, SPRING, Role.MANAGER)
    await sign_in_as(client, world, 20)
    as_admin = await client.post(
        CONTEST_INVITES, json={"grants": "admin", "username": "bob"}, headers=ORIGIN
    )
    assert (as_admin.status_code, as_admin.json()["code"]) == (403, "forbidden")
    at_org = await client.post(
        f"{ORG}/invites", json={"grants": "observer", "username": "bob"}, headers=ORIGIN
    )
    assert at_org.status_code == 403
    at_task = await client.post(
        f"{TASK}/invites", json={"grants": "contestant", "username": "bob"}, headers=ORIGIN
    )
    assert (at_task.status_code, at_task.json()["code"]) == (422, "invalid_invite")
    both = await client.post(
        CONTEST_INVITES,
        json={"grants": "observer", "username": "bob", "email": "b@example.test"},
        headers=ORIGIN,
    )
    assert both.json()["code"] == "invalid_invite"

    made = await client.post(
        CONTEST_INVITES, json={"grants": "observer", "username": "bob", "days": 1}, headers=ORIGIN
    )
    twice = await client.post(
        CONTEST_INVITES, json={"grants": "observer", "username": "bob"}, headers=ORIGIN
    )
    assert (twice.status_code, twice.json()["code"]) == (409, "already_invited")
    too_long = await client.post(
        CONTEST_INVITES, json={"grants": "observer", "username": "bob", "days": 91}, headers=ORIGIN
    )
    assert too_long.status_code == 422

    clock.advance(timedelta(days=1))
    await sign_in_as(client, world, 8)
    lapsed = await client.post(f"/api/v1/me/invites/{made.json()['id']}/accept", headers=ORIGIN)
    assert (lapsed.status_code, lapsed.json()["code"]) == (410, "invite_expired")


async def test_an_organiser_sends_an_invite_again_and_withdraws_it(
    client: httpx.AsyncClient, world: FakeForge, held_setup: Setup, clock: FakeClock
) -> None:
    await sign_in(client, world)
    made = (
        await client.post(
            CONTEST_INVITES, json={"grants": "observer", "email": "x@example.test"}, headers=ORIGIN
        )
    ).json()
    await held_setup.settle()
    first = _token(world)

    early = await client.post(f"{CONTEST_INVITES}/{made['id']}/send-again", headers=ORIGIN)
    assert (early.status_code, early.json()["code"]) == (429, "invite_limit")
    assert "Retry-After" in early.headers
    clock.advance(timedelta(minutes=10))
    again = await client.post(f"{CONTEST_INVITES}/{made['id']}/send-again", headers=ORIGIN)
    assert again.status_code == 200, again.text
    await held_setup.settle()
    assert _token(world) != first
    withdrawn = await client.post(f"{CONTEST_INVITES}/{made['id']}/withdraw", headers=ORIGIN)

    assert withdrawn.json()["status"] == "withdrawn"
    elsewhere = await client.post(f"{ORG}/invites/{made['id']}/withdraw", headers=ORIGIN)
    assert elsewhere.status_code == 404


async def test_an_observer_reads_the_list_and_changes_nothing(
    client: httpx.AsyncClient, world: FakeForge, held_setup: Setup
) -> None:
    made = (
        await client.post(
            CONTEST_INVITES, json={"grants": "admin", "email": "x@example.test"}, headers=ORIGIN
        )
    ).json()
    await world.orgs.grant_role(20, SPRING, Role.OBSERVER)
    await sign_in_as(client, world, 20)

    assert (await client.get(CONTEST_INVITES)).status_code == 200
    created = await client.post(
        CONTEST_INVITES, json={"grants": "observer", "username": "bob"}, headers=ORIGIN
    )
    assert created.status_code == 403
    for action in ("send-again", "withdraw"):
        refused = await client.post(f"{CONTEST_INVITES}/{made['id']}/{action}", headers=ORIGIN)
        assert refused.status_code == 403, action

    # A manager who is not an admin cannot act on an admin's invite either.
    await world.orgs.grant_role(20, SPRING, Role.MANAGER)
    await sign_in_as(client, world, 20)
    withdrawn = await client.post(f"{CONTEST_INVITES}/{made['id']}/withdraw", headers=ORIGIN)
    assert (withdrawn.status_code, withdrawn.json()["code"]) == (403, "forbidden")


async def test_the_persons_routes_need_a_session(
    client: httpx.AsyncClient, world: FakeForge
) -> None:
    client.cookies.clear()
    assert (await client.get("/api/v1/me/invites")).status_code == 401
    opened = await client.post("/api/v1/me/invites/open", json={"token": "x"}, headers=ORIGIN)
    assert opened.status_code == 401
