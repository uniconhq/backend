"""Making a task in a contest answers at once, the poller makes it with its
starter files, the status route follows it, and the contest lists it. A new
task's head is a draft with nothing wrong and no publication; a task in a
contest that is not there is not found.
"""

import httpx
from forge.testing import FakeForge, Setup, tick

from tests.integration.conftest import CONTEST, ORG, ORIGIN, TASK, sign_in


async def test_a_task_is_asked_for_made_by_the_poller_and_listed(
    client: httpx.AsyncClient, acme: FakeForge, held_setup: Setup
) -> None:
    await sign_in(client, acme)
    await client.post(f"{ORG}/contests", json={"name": "spring"}, headers=ORIGIN)
    await tick(held_setup, "provisioning")

    asked = await client.post(
        f"{CONTEST}/tasks", json={"name": "sum", "title": "Sum of Two"}, headers=ORIGIN
    )

    assert asked.status_code == 202
    assert (asked.json()["kind"], asked.json()["target"], asked.json()["status"]) == (
        "task",
        "acme/spring/sum",
        "pending",
    )
    await tick(held_setup, "provisioning")
    done = (await client.get(f"{TASK}/provisioning")).json()
    assert (done["status"], done["last_step"]) == ("ready", "roles")
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


async def test_a_task_nothing_asked_for_is_not_found(
    client: httpx.AsyncClient, sum_task: FakeForge
) -> None:
    missing = await client.get(f"{CONTEST}/tasks/product/provisioning")

    assert missing.status_code == 404
