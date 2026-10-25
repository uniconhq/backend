"""A delayed submission held to the most submissions, over HTTP (#445): one
retried once its entrant has no room left ends `over_limit`, which the
organisers' list says beforehand, the retry answers, and its contestant
reads with the most they reached.
"""

from datetime import timedelta

import httpx
from forge.testing import FakeClock, FakeForge

from tests.integration.conftest import ORIGIN, TASK, edit_task, sign_in_as, upload

SOURCE = b"print(sum(map(int, input().split())))\n"
STUCK = timedelta(hours=2)
"""How long a dispatched grading waits for a machine before it reads as a
system error."""


async def _submit(client: httpx.AsyncClient, forge: FakeForge, key: str) -> str:
    """A submission of acme/spring/sum by whoever is signed in; its grading."""
    made = await upload(client, forge, SOURCE)
    submitted = await client.post(
        f"{TASK}/submissions",
        json={
            "idempotency_key": key,
            "inputs": {
                "code": {"uploads": [made["id"]]},
                "language": {"value": "python"},
            },
        },
        headers=ORIGIN,
    )
    assert submitted.status_code == 201, submitted.text
    grading: str = submitted.json()["grading"]["id"]
    return grading


async def test_a_delayed_submission_retried_without_room_ends_over_the_limit(
    client: httpx.AsyncClient, entered: FakeForge, clock: FakeClock
) -> None:
    await sign_in_as(client, entered, 7)
    await edit_task(client, "scoring:", "submissions: {max: 1}\nscoring:")
    await sign_in_as(client, entered, 20)
    first = await _submit(client, entered, "key-0001-aaaa")
    clock.advance(STUCK)
    # Delayed, the first uses up nothing, so a second is taken, and waits.
    await _submit(client, entered, "key-0002-bbbb")
    await sign_in_as(client, entered, 7)

    listed = await client.get(f"{TASK}/gradings")
    retried = await client.post(f"{TASK}/gradings/{first}/retry", headers=ORIGIN)
    await sign_in_as(client, entered, 20)
    mine = await client.get(f"{TASK}/submissions/1")

    told = {
        entry["grading"]["submission_number"]: entry["grading"]["retry_limit"]
        for entry in listed.json()
    }
    assert told == {1: 1, 2: None}
    assert retried.status_code == 200, retried.text
    assert (retried.json()["attempt"], retried.json()["status"], retried.json()["limit"]) == (
        2,
        "over_limit",
        1,
    )
    shown = mine.json()["grading"]
    assert (shown["status"], shown["limit"], shown["runs"]) == ("over_limit", 1, [])
