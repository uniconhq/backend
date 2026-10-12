"""Taking a task out of its contest through the routes: the organisers' task
list says what it would do and how many submissions the task has, a task
nobody submitted to is removed, one with a submission is withdrawn, kept
from entrants and their submits until it is put back, and a request that
would now do the other than the organiser confirmed is refused with the
count as it is now. Only a manager of the contest may.
"""

import httpx
from forge.testing import FakeForge

from tests.integration.conftest import CONTEST, ORIGIN, TASK, sign_in_as, upload

STANDINGS = f"{CONTEST}/organise/tasks"


async def _submit(client: httpx.AsyncClient, forge: FakeForge, key: str) -> httpx.Response:
    made = await upload(client, forge, f"print({key!r})\n".encode())
    return await client.post(
        f"{TASK}/submissions",
        json={
            "idempotency_key": key,
            "inputs": {
                "submission": {"uploads": [made["id"]]},
                "language": {"value": "python"},
            },
        },
        headers=ORIGIN,
    )


async def _standing(client: httpx.AsyncClient) -> tuple[bool, int, str | None]:
    (row,) = (await client.get(STANDINGS)).json()
    return row["withdrawn"], row["submissions"], row["take_out"]


async def test_a_task_nobody_submitted_to_is_removed(
    client: httpx.AsyncClient, entered: FakeForge
) -> None:
    await sign_in_as(client, entered, 7)
    assert await _standing(client) == (False, 0, "remove")

    removed = await client.post(f"{TASK}/take-out", json={"confirmed": "remove"}, headers=ORIGIN)

    assert removed.status_code == 200, removed.text
    assert removed.json() == {"done": "remove"}
    assert (await client.get(STANDINGS)).json() == []
    assert (await client.get(f"{CONTEST}/tasks")).json() == []


async def test_a_task_with_a_submission_is_withdrawn_from_entrants_until_put_back(
    client: httpx.AsyncClient, entered: FakeForge
) -> None:
    submitted = await _submit(client, entered, "key-0001-aaaa")
    assert submitted.status_code == 201, submitted.text
    await sign_in_as(client, entered, 7)
    assert await _standing(client) == (False, 1, "withdraw")

    changed = await client.post(f"{TASK}/take-out", json={"confirmed": "remove"}, headers=ORIGIN)
    withdrawn = await client.post(
        f"{TASK}/take-out", json={"confirmed": "withdraw"}, headers=ORIGIN
    )

    assert changed.status_code == 409, changed.text
    assert (changed.json()["code"], changed.json()["submissions"]) == ("take_out_changed", 1)
    assert changed.json()["take_out"] == "withdraw"
    assert withdrawn.json() == {"done": "withdraw"}
    assert await _standing(client) == (True, 1, None)

    await sign_in_as(client, entered, 20)
    home = (await client.get(f"{CONTEST}/home")).json()
    refused = await _submit_refused(client)
    assert home["tasks"] == []
    assert (await client.get(f"{TASK}/page")).status_code == 404
    assert (refused.status_code, refused.json()["code"]) == (403, "task_withdrawn")

    await sign_in_as(client, entered, 7)
    returned = await client.post(f"{TASK}/put-back", headers=ORIGIN)

    assert returned.status_code == 200, returned.text
    assert returned.json() == {"notes": []}
    assert await _standing(client) == (False, 1, "withdraw")
    await sign_in_as(client, entered, 20)
    assert [task["name"] for task in (await client.get(f"{CONTEST}/home")).json()["tasks"]] == [
        "sum"
    ]


async def _submit_refused(client: httpx.AsyncClient) -> httpx.Response:
    """A submit of typed values alone, which a withdrawn task refuses before
    any upload is asked for.
    """
    return await client.post(
        f"{TASK}/submissions",
        json={"idempotency_key": "key-0002-bbbb", "inputs": {"language": {"value": "python"}}},
        headers=ORIGIN,
    )


async def test_only_a_manager_of_the_contest_takes_a_task_out(
    client: httpx.AsyncClient, entered: FakeForge
) -> None:
    refused = await client.post(f"{TASK}/take-out", json={"confirmed": "remove"}, headers=ORIGIN)
    put_back = await client.post(f"{TASK}/put-back", headers=ORIGIN)

    assert (refused.status_code, refused.json()["code"]) == (403, "forbidden")
    assert (put_back.status_code, put_back.json()["code"]) == (403, "forbidden")
