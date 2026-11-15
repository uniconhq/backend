"""A grading that ends in `system_error` is tried again once by itself, over
HTTP: the sweep that settles a stuck one starts the retry, and the
organiser's list of the task's gradings marks the new attempt `automatic`.
"""

import httpx
import pytest
from forge.testing import APP_URL, FORGE_URL, FakeClock, FakeForge, Settings

from tests.integration.conftest import ORIGIN, TASK, sign_in_as, stuck, upload

SOURCE = b"print(sum(map(int, input().split())))\n"


@pytest.fixture
def settings(migrated_database_url: str) -> Settings:
    return Settings.for_tests(
        database_url=migrated_database_url,
        public_url=APP_URL,
        forge_public_url=FORGE_URL,
        retry_failed=True,
    )


async def test_the_sweep_retries_a_stuck_grading_and_the_list_says_the_platform_did(
    client: httpx.AsyncClient, entered: FakeForge, clock: FakeClock
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
    await stuck(client, clock)

    read = await client.get(f"{TASK}/submissions/1")
    await sign_in_as(client, entered, 7)
    listed = await client.get(f"{TASK}/gradings")

    assert read.status_code == 200, read.text
    rows = [entry["grading"] for entry in listed.json()]
    assert [(row["attempt"], row["status"], row["automatic"]) for row in rows] == [
        (2, "dispatched", True),
        (1, "system_error", False),
    ]
