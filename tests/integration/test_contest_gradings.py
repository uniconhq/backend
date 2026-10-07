"""A contest's gradings over HTTP, for an observer of the contest: the feed,
newest first, each row the grading with its task by name and who submitted
it, narrowed by task, by username, by team and by status, a stuck grading
read as `system_error` and one staff cancelled with their sentence; and the
queue depth, counted by status. Someone holding a role at a task alone, and
a contestant, are refused both, and both need a session.
"""

from datetime import timedelta

import httpx
from forge.api.types import Role
from forge.testing import FakeClock, FakeForge, Setup

from tests.integration.conftest import CONTEST, ORIGIN, SUM, TASK, enter, sign_in_as, upload

SOURCE = b"print(sum(map(int, input().split())))\n"
FEED = f"{CONTEST}/gradings"
QUEUE = f"{CONTEST}/gradings/queue"
STUCK = timedelta(hours=2)


async def _submit(client: httpx.AsyncClient, forge: FakeForge) -> str:
    """A submission of acme/spring/sum by whoever is signed in; its grading."""
    made = await upload(client, forge, SOURCE)
    submitted = await client.post(
        f"{TASK}/submissions",
        json={
            "idempotency_key": "key-0001-aaaa",
            "inputs": {
                "submission": {"uploads": [made["id"]]},
                "language": {"value": "python"},
            },
        },
        headers=ORIGIN,
    )
    assert submitted.status_code == 201, submitted.text
    grading: str = submitted.json()["grading"]["id"]
    return grading


async def _two(client: httpx.AsyncClient, entered: FakeForge, held_setup: Setup) -> tuple[str, str]:
    """carol's grading and then bob's, with ada signed in."""
    carols = await _submit(client, entered)
    await enter(client, entered, held_setup, 8)
    bobs = await _submit(client, entered)
    await sign_in_as(client, entered, 7)
    return carols, bobs


async def test_an_observer_reads_the_contests_gradings_newest_first(
    client: httpx.AsyncClient, entered: FakeForge, held_setup: Setup
) -> None:
    carols, bobs = await _two(client, entered, held_setup)

    listed = await client.get(FEED)

    assert listed.status_code == 200, listed.text
    rows = listed.json()
    assert [row["grading"]["id"] for row in rows] == [bobs, carols]
    assert [row["task"] for row in rows] == ["sum", "sum"]
    assert [row["by"] for row in rows] == [
        {"user_id": 8, "team": None, "name": "bob"},
        {"user_id": 20, "team": None, "name": "carol"},
    ]
    first = rows[1]["grading"]
    assert (first["submission_number"], first["attempt"], first["status"]) == (
        1,
        1,
        "dispatched",
    )
    assert first["cancel_reason"] is None


async def test_the_feed_narrows_by_task_user_team_and_status(
    client: httpx.AsyncClient, entered: FakeForge, held_setup: Setup
) -> None:
    carols, bobs = await _two(client, entered, held_setup)

    async def ids(**query: str | int) -> list[str]:
        answer = await client.get(FEED, params=query)
        assert answer.status_code == 200, answer.text
        return [row["grading"]["id"] for row in answer.json()]

    assert await ids(task="sum") == [bobs, carols]
    assert await ids(task="product") == []
    assert await ids(user="carol") == [carols]
    assert await ids(user="nobody-here") == []
    assert await ids(team="0192f4a4-7b7e-7000-8000-000000000001") == []
    assert await ids(status="dispatched") == [bobs, carols]
    assert await ids(status="system_error") == []
    assert await ids(limit=1) == [bobs]


async def test_a_stuck_grading_reads_as_a_system_error_and_a_cancelled_one_says_why(
    client: httpx.AsyncClient, entered: FakeForge, held_setup: Setup, clock: FakeClock
) -> None:
    carols, bobs = await _two(client, entered, held_setup)
    clock.advance(STUCK)
    reason = "The checker crashed on this one; it is not counted."
    await client.post(f"{TASK}/gradings/{carols}/cancel", json={"reason": reason}, headers=ORIGIN)

    stuck = await client.get(FEED, params={"status": "system_error"})
    cancelled = await client.get(FEED, params={"status": "cancelled"})

    assert [row["grading"]["id"] for row in stuck.json()] == [bobs]
    assert stuck.json()[0]["grading"]["error"]
    assert [row["grading"]["id"] for row in cancelled.json()] == [carols]
    assert cancelled.json()[0]["grading"]["cancel_reason"] == reason


async def test_a_query_that_is_not_one_is_a_validation_error(
    client: httpx.AsyncClient, entered: FakeForge
) -> None:
    await sign_in_as(client, entered, 7)

    answers = [
        await client.get(FEED, params={"limit": 501}),
        await client.get(FEED, params={"limit": 0}),
        await client.get(FEED, params={"status": "lost"}),
        await client.get(FEED, params={"team": "not-a-team"}),
    ]

    assert [(answer.status_code, answer.json()["code"]) for answer in answers] == [
        (422, "validation_error")
    ] * 4


async def test_the_queue_depth_counts_the_gradings_waiting_by_status(
    client: httpx.AsyncClient, entered: FakeForge, held_setup: Setup, clock: FakeClock
) -> None:
    await sign_in_as(client, entered, 7)
    empty = await client.get(QUEUE)
    await sign_in_as(client, entered, 20)
    await _two(client, entered, held_setup)

    waiting = await client.get(QUEUE)
    clock.advance(STUCK)
    stuck = await client.get(QUEUE)

    assert empty.status_code == 200, empty.text
    assert empty.json() == {"queued": 0, "dispatched": 0}
    assert waiting.json() == {"queued": 0, "dispatched": 2}
    assert stuck.json() == {"queued": 0, "dispatched": 0}


async def test_a_role_at_a_task_alone_or_none_is_refused_the_feed_and_the_queue(
    client: httpx.AsyncClient, entered: FakeForge
) -> None:
    await _submit(client, entered)
    as_contestant = [await client.get(FEED), await client.get(QUEUE)]
    await entered.orgs.grant_role(8, SUM, Role.MANAGER)
    await sign_in_as(client, entered, 8)
    as_task_manager = [await client.get(FEED), await client.get(QUEUE)]

    for refused in (*as_contestant, *as_task_manager):
        assert (refused.status_code, refused.json()["code"]) == (403, "forbidden")


async def test_the_feed_and_the_queue_need_a_session(
    client: httpx.AsyncClient, entered: FakeForge
) -> None:
    client.cookies.clear()

    for refused in (await client.get(FEED), await client.get(QUEUE)):
        assert (refused.status_code, refused.json()["code"]) == (401, "unauthenticated")
