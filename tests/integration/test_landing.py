"""The routes a visitor with no session calls. They answer with no cookie at
all: the public contests, one with its released tasks, and a released task's
statement. A contest that is not public and a task that is not released
answer as not found, and every other route of the contestant's and the
organiser's path refuses a request with no session.
"""

import httpx
from forge.testing import FakeForge

from tests.integration.conftest import CONTEST, ORG, ORIGIN, TASK, publish, run_contest

PUBLIC = "/api/v1/public/contests"


async def test_a_visitor_reads_the_public_contests_and_a_released_statement(
    client: httpx.AsyncClient, sum_task: FakeForge
) -> None:
    await run_contest(client, visibility="everyone")
    await publish(client)
    client.cookies.clear()

    listed = await client.get(PUBLIC)
    contest = await client.get(f"{PUBLIC}/acme/spring")
    statement = await client.get(f"{PUBLIC}/acme/spring/tasks/sum")

    assert [(entry["where"], entry["tasks"]) for entry in listed.json()] == [
        ({"org": "acme", "contest": "spring"}, [])
    ]
    assert contest.json()["tasks"] == [{"name": "sum", "label": "A", "title": "sum"}]
    assert statement.json() == {
        "task": {"name": "sum", "label": "A", "title": "sum"},
        "statement": "Add two numbers.\n",
    }


async def test_what_is_not_public_answers_as_not_found(
    client: httpx.AsyncClient, sum_task: FakeForge
) -> None:
    await run_contest(client, visibility="signed-in")
    await publish(client)
    client.cookies.clear()

    answers = [
        await client.get(f"{PUBLIC}/acme/spring"),
        await client.get(f"{PUBLIC}/acme/spring/tasks/sum"),
        await client.get(f"{PUBLIC}/acme/nowhere"),
    ]

    assert (await client.get(PUBLIC)).json() == []
    assert [(answer.status_code, answer.json()["code"]) for answer in answers] == [
        (404, "not_found")
    ] * 3


async def test_a_task_not_released_yet_is_not_found(
    client: httpx.AsyncClient, sum_task: FakeForge
) -> None:
    await run_contest(client, visibility="everyone")
    client.cookies.clear()

    unpublished = await client.get(f"{PUBLIC}/acme/spring/tasks/sum")
    contest = await client.get(f"{PUBLIC}/acme/spring")

    assert (unpublished.status_code, unpublished.json()["code"]) == (404, "not_found")
    assert contest.json()["tasks"] == []


async def test_every_other_route_refuses_a_request_with_no_session(
    client: httpx.AsyncClient, sum_task: FakeForge
) -> None:
    await run_contest(client, visibility="everyone")
    client.cookies.clear()

    answers = [
        await client.get("/api/v1/contests"),
        await client.get(f"{CONTEST}/home"),
        await client.get(f"{TASK}/page"),
        await client.get(f"{CONTEST}/registration"),
        await client.post(f"{CONTEST}/registration", json={}, headers=ORIGIN),
        await client.get(f"{CONTEST}/contestants"),
        await client.get(f"{ORG}/contests"),
    ]

    assert {answer.status_code for answer in answers} == {401}
