"""Making a task in a contest makes it with its starter files before the
request answers, and the contest lists it. A new task's head is a draft with
nothing wrong and no publication; a task in a contest that is not there is
not found.
"""

import httpx
from forge.testing import FakeForge, Setup

from tests.integration.conftest import CONTEST, ORG, ORIGIN, TASK, sign_in


async def test_a_task_is_made_and_listed(
    client: httpx.AsyncClient, acme: FakeForge, held_setup: Setup
) -> None:
    await sign_in(client, acme)
    await client.post(f"{ORG}/contests", json={"name": "spring"}, headers=ORIGIN)

    made = await client.post(
        f"{CONTEST}/tasks", json={"name": "sum", "title": "Sum of Two"}, headers=ORIGIN
    )

    assert made.status_code == 201
    assert made.json() == {"name": "sum"}
    assert (await client.get(f"{CONTEST}/tasks")).json() == [{"name": "sum"}]
    settings = (await client.get(f"{TASK}/files/task.yaml")).json()
    assert 'name: "Sum of Two"' in settings["content"]


async def test_a_new_task_is_an_unsaved_draft_with_nothing_wrong(
    client: httpx.AsyncClient, sum_task: FakeForge
) -> None:
    state = await client.get(TASK)

    assert state.status_code == 200
    body = state.json()
    assert (body["latest"], body["draft"], body["errors"]) == (None, True, [])
    assert body["head"]
    assert (await client.get(f"{TASK}/publications")).json() == []


async def test_a_task_in_a_contest_that_is_not_there_is_not_found(
    client: httpx.AsyncClient, acme: FakeForge
) -> None:
    await sign_in(client, acme)

    refused = await client.post(
        f"{ORG}/contests/autumn/tasks", json={"name": "sum"}, headers=ORIGIN
    )

    assert refused.status_code == 404
    assert refused.json()["code"] == "not_found"
