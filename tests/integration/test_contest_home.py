"""What a signed-in person reads of a contest, over HTTP: the list of contests
they see with their status, a contest's home with its released tasks and
their own deadline, and a released task's page with its statement and
limits. A contest they may not see and a task that is not visible answer as
not found.
"""

import httpx
from forge.testing import FakeForge

from tests.integration.conftest import CONTEST, ORIGIN, TASK, publish, run_contest, sign_in_as


async def test_a_signed_in_person_reads_the_home_and_a_released_task(
    client: httpx.AsyncClient, world: FakeForge
) -> None:
    await run_contest(client, visibility="signed-in")
    await publish(client)
    await sign_in_as(client, world, 20)

    listed = await client.get("/api/v1/contests")
    home = await client.get(f"{CONTEST}/home")
    page = await client.get(f"{TASK}/page")

    assert [(entry["org"], entry["name"], entry["status"]) for entry in listed.json()] == [
        ("acme", "spring", None)
    ]
    body = home.json()
    assert (body["org"], body["name"], body["state"]) == ("acme", "spring", "published")
    assert (body["registration"], body["organises"], body["registration_open"]) == (
        None,
        False,
        True,
    )
    assert body["asks_code"] is False
    assert body["deadline"] == body["end"] == "2026-09-26T15:00:00Z"
    assert body["now"] == "2026-09-26T12:00:00Z"
    assert [(task["name"], task["release"]["open"]) for task in body["tasks"]] == [("sum", True)]
    assert page.json()["statement"] == "Add two numbers.\n"
    assert page.json()["limits"] == {
        "submissions": 50,
        "rate_count": 1,
        "rate_seconds": 30,
        "max_size": 10 * 1024 * 1024,
    }
    assert [(entry["id"], entry["type"], entry["label"]) for entry in page.json()["inputs"]] == [
        ("submission", "code", "Your solution")
    ]


async def test_the_home_carries_the_callers_registration(
    client: httpx.AsyncClient, world: FakeForge
) -> None:
    await run_contest(client, visibility="public")
    await sign_in_as(client, world, 20)
    await client.post(f"{CONTEST}/registration", json={}, headers=ORIGIN)

    home = await client.get(f"{CONTEST}/home")
    listed = await client.get("/api/v1/contests")

    assert home.json()["registration"]["status"] == "pending"
    assert listed.json()[0]["status"] == "pending"


async def test_a_hidden_contest_and_an_unreleased_task_are_not_found(
    client: httpx.AsyncClient, world: FakeForge
) -> None:
    await run_contest(client, visibility="signed-in")
    await sign_in_as(client, world, 20)
    unreleased = await client.get(f"{TASK}/page")

    await sign_in_as(client, world, 7)
    await run_contest(client, visibility="hidden")
    await sign_in_as(client, world, 20)
    hidden = await client.get(f"{CONTEST}/home")

    assert (unreleased.status_code, unreleased.json()["code"]) == (404, "not_found")
    assert (hidden.status_code, hidden.json()["code"]) == (404, "not_found")
    assert (await client.get("/api/v1/contests")).json() == []


async def test_the_contestant_reads_need_a_session(
    client: httpx.AsyncClient, world: FakeForge
) -> None:
    client.cookies.clear()

    for path in ("/api/v1/contests", f"{CONTEST}/home", f"{TASK}/page"):
        answer = await client.get(path)
        assert (answer.status_code, answer.json()["code"]) == (401, "unauthenticated"), path
