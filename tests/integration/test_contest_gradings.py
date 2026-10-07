"""A contest's gradings over HTTP, for an observer of the contest: the feed,
newest first, each row the grading, whether it is its submission's latest
attempt, its task by name and letter and who submitted it, narrowed by
task, by username, by team and by status, a stuck grading read as
`system_error` and one staff cancelled with their sentence; a username or a
team that cannot be one a validation error; and the queue depth, counted by
status. Someone holding a role at some of its tasks alone reads both over
those tasks, a contestant is refused both, and both need a session.
"""

from datetime import timedelta

import httpx
from forge.api.types import Role, Scope
from forge.testing import FakeClock, FakeForge, Setup, name_places

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
    assert [(row["task"], row["label"]) for row in rows] == [("sum", "A"), ("sum", "A")]
    assert [row["grading"]["latest"] for row in rows] == [True, True]
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
        await client.get(FEED, params={"user": "bob/repos"}),
        await client.get(FEED, params={"user": "../admin"}),
        await client.get(FEED, params={"user": "-bob"}),
        await client.get(FEED, params={"user": "bo..b"}),
        await client.get(FEED, params={"user": "b" * 41}),
    ]

    assert [(answer.status_code, answer.json()["code"]) for answer in answers] == [
        (422, "validation_error")
    ] * 9
    assert (await client.get(FEED, params={"user": "b" * 40})).status_code == 200


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


async def test_a_role_at_some_tasks_reads_their_gradings_alone(
    client: httpx.AsyncClient, entered: FakeForge, held_setup: Setup
) -> None:
    await name_places(held_setup, "acme/spring/product")
    carols = await _submit(client, entered)
    await entered.orgs.grant_role(8, SUM, Role.MANAGER)
    entered.add_user(30, "dave")
    await entered.orgs.grant_role(30, Scope("acme", "spring", "product"), Role.OBSERVER)

    await sign_in_as(client, entered, 8)
    of_sum = [await client.get(FEED), await client.get(QUEUE)]
    await sign_in_as(client, entered, 30)
    of_product = [
        await client.get(FEED),
        await client.get(QUEUE),
        await client.get(FEED, params={"task": "sum"}),
    ]

    assert [answer.status_code for answer in (*of_sum, *of_product)] == [200] * 5
    assert [row["grading"]["id"] for row in of_sum[0].json()] == [carols]
    assert of_sum[1].json() == {"queued": 0, "dispatched": 1}
    assert (of_product[0].json(), of_product[2].json()) == ([], [])
    assert of_product[1].json() == {"queued": 0, "dispatched": 0}


async def test_no_role_in_the_contest_is_refused_the_feed_and_the_queue(
    client: httpx.AsyncClient, entered: FakeForge, held_setup: Setup
) -> None:
    await _submit(client, entered)
    as_contestant = [await client.get(FEED), await client.get(QUEUE)]
    await name_places(held_setup, "acme/autumn")
    await entered.orgs.grant_role(8, Scope("acme", "autumn"), Role.ADMIN)
    await sign_in_as(client, entered, 8)
    elsewhere = [await client.get(FEED), await client.get(QUEUE)]

    for refused in (*as_contestant, *elsewhere):
        assert (refused.status_code, refused.json()["code"]) == (403, "forbidden")
        assert refused.json()["detail"] == (
            "This needs a role at acme/spring or at anything in it."
        )


async def test_the_feed_and_the_queue_need_a_session(
    client: httpx.AsyncClient, entered: FakeForge
) -> None:
    client.cookies.clear()

    for refused in (await client.get(FEED), await client.get(QUEUE)):
        assert (refused.status_code, refused.json()["code"]) == (401, "unauthenticated")
