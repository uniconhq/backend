"""A save answers preparing and the polling route returns its publication."""

import httpx
from forge.testing import FakeForge, Setup

from tests.integration.conftest import ORIGIN, TASK, read


async def test_the_saved_environment_prepares_and_publishes_through_the_task_routes(
    client: httpx.AsyncClient, sum_task: FakeForge, held_setup: Setup
) -> None:
    before = await read(client, f"{TASK}/files/task.yaml")
    saved = await client.post(
        f"{TASK}/save",
        headers=ORIGIN,
        json={
            "changes": [
                {
                    "path": "task.yaml",
                    "token": before["token"],
                    "content": before["content"]
                    + '\nenvironment:\n  cpp: {version: "16"}\n  python:\n    packages: [numpy]\n',
                }
            ],
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
    lock = await read(client, f"{TASK}/files/environment.lock")
    assert '"linux-aarch64"' in lock["content"] and '"linux-64"' in lock["content"]

    state = (await client.get(TASK)).json()
    assert state["toolchains"] == {
        "cpp": {"picked": "gxx 16", "version": "16"},
        "python": {"picked": "python 3.15.2", "version": None},
    }
