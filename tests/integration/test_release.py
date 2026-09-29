"""Whether a task is released to the caller: nothing before its first
publication, released and open once the contest is published and running,
and no such task for someone the contest is hidden from.
"""

import httpx
from forge.testing import FakeForge

from tests.integration.conftest import TASK, publish, run_contest, sign_in_as


async def test_a_task_is_released_to_a_person_once_it_is_published_and_the_contest_runs(
    client: httpx.AsyncClient, sum_task: FakeForge
) -> None:
    await run_contest(client)
    await sign_in_as(client, sum_task, 8)
    before = await client.get(f"{TASK}/release")

    await sign_in_as(client, sum_task, 7)
    await publish(client)
    await sign_in_as(client, sum_task, 8)
    after = await client.get(f"{TASK}/release")

    assert before.json() == {
        "released": False,
        "visible": False,
        "open": False,
        "closed": "not_released",
    }
    assert after.json() == {"released": True, "visible": True, "open": True, "closed": None}


async def test_a_task_in_a_contest_hidden_from_the_caller_is_not_found(
    client: httpx.AsyncClient, sum_task: FakeForge
) -> None:
    await run_contest(client, visibility="hidden")
    await publish(client)
    await sign_in_as(client, sum_task, 8)

    answer = await client.get(f"{TASK}/release")

    assert answer.status_code == 404
    assert answer.json()["code"] == "not_found"


async def test_the_release_needs_a_session(client: httpx.AsyncClient, sum_task: FakeForge) -> None:
    client.cookies.clear()

    assert (await client.get(f"{TASK}/release")).status_code == 401
