"""A contest's and a task's settings as their form's values through the
routes: read by an observer, a contest's saved by a manager with every
comment of the file kept, a task's saved with the task, and the refusals a
save meets: a stale token, an admin-only key changed by a manager, two
entries with one name, and an observer's save; and the runs a task's draft
makes.
"""

from typing import Any

import httpx
from forge.api.types import Role
from forge.testing import FakeForge

from tests.integration.conftest import CONTEST, ORIGIN, SPRING, TASK, prepared, read, sign_in_as


async def _put(client: httpx.AsyncClient, values: dict[str, Any], token: str | None) -> Any:
    response = await client.put(
        f"{CONTEST}/settings", json={"values": values, "token": token}, headers=ORIGIN
    )
    return await prepared(client, response)


async def _commented(client: httpx.AsyncClient) -> str:
    before = await read(client, f"{CONTEST}/files/contest.yaml")
    text = before["content"].replace("state: draft", "state: draft  # not open yet")
    text = "# Our spring round.\n" + text
    written = await client.put(
        f"{CONTEST}/files/contest.yaml",
        json={"content": text, "token": before["token"]},
        headers=ORIGIN,
    )
    assert written.status_code == 200
    return str(text)


async def test_saving_the_contests_values_keeps_every_comment(
    client: httpx.AsyncClient, sum_task: FakeForge
) -> None:
    text = await _commented(client)
    read_back = await read(client, f"{CONTEST}/settings")
    values = read_back["values"]
    values["description"] = "Two hours"

    written = await _put(client, values, read_back["token"])

    assert written.status_code == 200
    assert written.json()["version"]
    after = await read(client, f"{CONTEST}/files/contest.yaml")
    assert after["content"] == text + "description: Two hours\n"


async def test_a_task_reads_its_values_and_saves_them_with_the_task(
    client: httpx.AsyncClient, sum_task: FakeForge
) -> None:
    settings = await read(client, f"{TASK}/settings")
    values = settings["values"]
    assert values["scoring"]["values"][0]["name"] == "score"
    values["name"] = "Sum of Three"

    saved = await client.post(
        f"{TASK}/save",
        json={"changes": [{"path": "task.yaml", "token": settings["token"], "values": values}]},
        headers=ORIGIN,
    )
    saved = await prepared(client, saved)

    assert saved.status_code == 200
    after = await read(client, f"{TASK}/files/task.yaml")
    assert after["content"].startswith("# The task's settings.")
    assert 'name: "Sum of Three"\n' in after["content"]


async def test_a_stale_token_is_a_conflict(client: httpx.AsyncClient, sum_task: FakeForge) -> None:
    settings = await read(client, f"{CONTEST}/settings")
    await _commented(client)

    stale = await _put(client, settings["values"], settings["token"])

    assert stale.status_code == 409
    assert stale.json()["code"] == "conflict"


async def test_a_managers_change_to_an_admin_only_key_is_refused(
    client: httpx.AsyncClient, sum_task: FakeForge
) -> None:
    await sum_task.orgs.grant_role(8, SPRING, Role.MANAGER)
    await sign_in_as(client, sum_task, 8)
    settings = await read(client, f"{CONTEST}/settings")

    refused = await _put(client, {**settings["values"], "name": "Autumn"}, settings["token"])

    assert refused.status_code == 403
    assert refused.json()["code"] == "admin_only"
    assert refused.json()["keys"] == ["name"]


async def test_two_leaderboards_with_one_key_are_refused_at_that_key(
    client: httpx.AsyncClient, sum_task: FakeForge
) -> None:
    settings = await read(client, f"{CONTEST}/settings")
    board = {"key": "main", "title": "Main"}

    refused = await _put(
        client, {**settings["values"], "leaderboards": [board, board]}, settings["token"]
    )

    assert refused.status_code == 422
    assert refused.json()["code"] == "invalid_definition"
    assert [error["path"] for error in refused.json()["errors"]] == [["leaderboards", "main"]]


async def test_an_observer_reads_the_values_and_may_not_save_them(
    client: httpx.AsyncClient, sum_task: FakeForge
) -> None:
    await sum_task.orgs.grant_role(9, SPRING, Role.OBSERVER)
    await sign_in_as(client, sum_task, 9)
    settings = await read(client, f"{CONTEST}/settings")

    refused = await _put(client, settings["values"], settings["token"])

    assert refused.status_code == 403


async def test_reading_the_settings_needs_a_role_there(
    client: httpx.AsyncClient, sum_task: FakeForge
) -> None:
    await sign_in_as(client, sum_task, 9)

    refused = await client.get(f"{CONTEST}/settings")

    assert refused.status_code in (403, 404)


async def test_a_drafts_runs_cross_its_axes(client: httpx.AsyncClient, sum_task: FakeForge) -> None:
    repeat = [
        {"inputs": ["input", "answer"], "tuples": [["a.in", "a.ans"], ["b.in", "b.ans"]]},
        {"inputs": ["seed"], "tuples": [{"title": "One", "seed": 1}]},
    ]

    answer = await client.post(f"{TASK}/draft-runs", json={"repeat": repeat}, headers=ORIGIN)

    assert answer.status_code == 200
    body = answer.json()
    assert body["count"] == 2
    assert body["runs"] == [
        {"titles": ["One"], "cells": {"input": "a.in", "answer": "a.ans", "seed": 1}},
        {"titles": ["One"], "cells": {"input": "b.in", "answer": "b.ans", "seed": 1}},
    ]
    assert [len(axis) for axis in body["axes"]] == [2, 1]
