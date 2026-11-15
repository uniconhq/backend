"""A save answers preparing and the polling route returns its publication."""

import httpx
from forge.testing import FakeForge, Setup

from tests.integration.conftest import ORIGIN, TASK, read


async def test_the_saved_environment_prepares_and_publishes_through_the_task_routes(
    client: httpx.AsyncClient, sum_task: FakeForge, held_setup: Setup
) -> None:
    before = await read(client, f"{TASK}/request")
    environment = {"cpp": {"version": "16"}, "python": {"packages": ["numpy"]}}
    saved = await client.post(
        f"{TASK}/save",
        headers=ORIGIN,
        json={
            "request": {
                "request": {**before["request"], "environment": environment},
                "token": before["token"],
            },
            "confirm": True,
        },
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["status"] == "preparing"
    await held_setup.settle()
    ready = await client.get(f"{TASK}/preparation")
    assert ready.status_code == 200, ready.text
    assert ready.json()["id"] == saved.json()["preparation"]
    assert ready.json()["status"] == "ready", ready.text
    assert ready.json()["result"]["number"] == 1
    data = await read(client, f"{TASK}/files/lock.json")
    assert "linux-aarch64" in data["content"] and "linux-64" in data["content"]

    state = (await client.get(TASK)).json()
    assert state["toolchains"] == {
        "cpp": {"picked": "gxx 16", "version": "16"},
        "python": {"picked": "python 3.15.2", "version": None},
    }
