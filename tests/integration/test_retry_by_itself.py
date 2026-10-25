"""A grading that ends in `system_error` is tried again once by itself, over
HTTP: the read that finds it failed starts the retry, and the organiser's
list of the task's gradings marks the new attempt `automatic`.
"""

from datetime import timedelta

import httpx
import pytest
from forge.testing import APP_URL, FORGE_URL, FakeClock, FakeForge, Settings, Setup

from tests.integration.conftest import ORIGIN, TASK, sign_in_as, upload

SOURCE = b"print(sum(map(int, input().split())))\n"
STUCK = timedelta(hours=2)
"""How long a dispatched grading waits for a machine before it reads as a
system error."""


@pytest.fixture
def settings(migrated_database_url: str) -> Settings:
    return Settings.for_tests(
        database_url=migrated_database_url,
        public_url=APP_URL,
        forge_public_url=FORGE_URL,
        retry_failed=True,
    )


async def test_a_read_that_finds_a_failure_retries_it_and_the_list_says_the_platform_did(
    client: httpx.AsyncClient, entered: FakeForge, clock: FakeClock, held_setup: Setup
) -> None:
    made = await upload(client, entered, SOURCE)
    submitted = await client.post(
        f"{TASK}/submissions",
        json={
            "idempotency_key": "key-0001-aaaa",
            "inputs": {
                "code": {"uploads": [made["id"]]},
                "language": {"value": "python"},
            },
        },
        headers=ORIGIN,
    )
    assert submitted.status_code == 201, submitted.text
    clock.advance(STUCK)

    read = await client.get(f"{TASK}/submissions/1")
    await held_setup.settle()
    await sign_in_as(client, entered, 7)
    listed = await client.get(f"{TASK}/gradings")

    assert read.status_code == 200, read.text
    rows = [entry["grading"] for entry in listed.json()]
    assert [(row["attempt"], row["status"], row["automatic"]) for row in rows] == [
        (2, "dispatched", True),
        (1, "system_error", False),
    ]
