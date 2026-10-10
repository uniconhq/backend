"""The save, which is how a task is published, through the routes: the whole
organiser path from an org through the poller to a publication number; a
save of the statement that does not change how the task grades; a save
that does not check, kept as a draft with its errors, which the task then
shows; the refusals, a path inside `plans/`, a manager's change to an
admin-only file and a grading change while the contest runs, which the same
save confirmed publishes; a change kept as a draft and published by an
empty confirmed save; and a stale token answered as a conflict.
"""

from typing import Any

import httpx
import pytest
from forge.api.types import Role
from forge.testing import FakeForge, Setup, seed_classic

from tests.integration.conftest import (
    CONTEST,
    ORG,
    ORIGIN,
    SUM,
    TASK,
    publish,
    read,
    run_contest,
    sign_in,
    sign_in_as,
)

MISSING = [
    {
        "path": "tests/main/",
        "message": "main is a folder of tests/ but not a group in test_groups: list it, or move "
        "its tests.",
    },
    {
        "path": "test_groups.hidden",
        "message": "There is no folder tests/hidden/ with a test in it.",
    },
]


def _change(path: str, content: str, token: str | None) -> dict[str, Any]:
    return {"path": path, "encoding": "utf-8", "content": content, "token": token}


async def _save(
    client: httpx.AsyncClient, *changes: dict[str, Any], **options: bool
) -> httpx.Response:
    return await client.post(
        f"{TASK}/save", json={"changes": list(changes), **options}, headers=ORIGIN
    )


async def _edit(client: httpx.AsyncClient, path: str, old: str, new: str) -> dict[str, Any]:
    """The file as read, with `old` replaced by `new`, as an editor sends it."""
    file = await read(client, f"{TASK}/files/{path}")
    assert old in file["content"]
    return _change(path, file["content"].replace(old, new), file["token"])


async def test_the_organiser_path_from_an_org_to_a_publication(
    client: httpx.AsyncClient, forge: FakeForge, held_setup: Setup
) -> None:
    await seed_classic(forge)
    await sign_in(client, forge)
    assert (await client.post("/api/v1/orgs", json={"name": "acme"}, headers=ORIGIN)).is_success
    await client.post(f"{ORG}/contests", json={"name": "spring"}, headers=ORIGIN)
    await client.post(f"{CONTEST}/tasks", json={"name": "sum"}, headers=ORIGIN)

    task_yaml = await read(client, f"{TASK}/files/task.yaml")
    written = await client.put(
        f"{TASK}/files/task.yaml",
        json={
            "encoding": "utf-8",
            "content": task_yaml["content"].replace("time_limit: 2", "time_limit: 3"),
            "token": task_yaml["token"],
        },
        headers=ORIGIN,
    )

    assert written.status_code == 200, written.text
    first = written.json()
    assert (first["number"], first["grading_changed"]) == (1, False)
    assert first["notes"] == [
        "Each group's most points: main 100.",
        "sum reveals at 2026-10-03T17:00:00+00:00.",
        "sum joins Standings.",
    ]

    statement = await _save(client, await _edit(client, "statement.md", "Write", "Add. Write"))
    assert (statement.json()["number"], statement.json()["grading_changed"]) == (2, False)

    broken = await _save(
        client,
        await _edit(client, "task.yaml", "main: {each: 100}", "hidden: {each: 100}"),
    )
    assert broken.status_code == 200
    draft = broken.json()
    assert (draft["errors"], draft["held_back"]) == (MISSING, [])

    state = (await client.get(TASK)).json()
    assert (state["head"], state["draft"], state["errors"]) == (draft["version"], True, MISSING)
    assert state["latest"]["number"] == 2
    published = (await client.get(f"{TASK}/publications")).json()
    assert [(entry["number"], entry["grading_changed"]) for entry in published] == [
        (1, False),
        (2, False),
    ]
    # The forge's id for a publication is built from keys, which stay home.
    assert all("id" not in entry for entry in published)


async def test_a_save_inside_plans_is_refused_naming_the_path(
    client: httpx.AsyncClient, sum_task: FakeForge
) -> None:
    refused = await _save(client, _change("plans/plan.json", "{}", None))

    assert refused.status_code == 403
    assert refused.json()["code"] == "reserved_path"
    assert refused.json()["paths"] == ["plans/plan.json"]


async def test_a_managers_change_to_the_statement_is_refused(
    client: httpx.AsyncClient, sum_task: FakeForge
) -> None:
    await sum_task.orgs.grant_role(8, SUM, Role.MANAGER)
    await sign_in_as(client, sum_task, 8)

    refused = await _save(client, await _edit(client, "statement.md", "Write", "Mine. Write"))

    assert refused.status_code == 403
    assert refused.json()["code"] == "admin_only"
    assert refused.json()["keys"] == ["statement.md"]


@pytest.fixture
async def running(client: httpx.AsyncClient, sum_task: FakeForge) -> FakeForge:
    """The task published once, in a contest running around the fake clock."""
    await run_contest(client)
    await publish(client)
    return sum_task


async def test_a_grading_change_while_the_contest_runs_asks_first(
    client: httpx.AsyncClient, running: FakeForge
) -> None:
    faster = await _edit(client, "task.yaml", "time_limit: 2", "time_limit: 1")

    asked = await _save(client, faster)

    assert asked.status_code == 409
    assert asked.json()["code"] == "confirmation_required"
    assert asked.json()["changes"] == ["plans/plan.json changed"]
    assert asked.json()["regrades"] == 0
    assert len((await client.get(f"{TASK}/publications")).json()) == 1

    confirmed = await _save(client, faster, confirm=True)

    assert confirmed.status_code == 200
    assert (confirmed.json()["number"], confirmed.json()["grading_changed"]) == (2, True)
    assert confirmed.json()["changes"] == ["plans/plan.json changed"]


async def test_a_change_kept_as_a_draft_is_published_by_an_empty_confirmed_save(
    client: httpx.AsyncClient, running: FakeForge
) -> None:
    faster = await _edit(client, "task.yaml", "time_limit: 2", "time_limit: 1")

    kept = await _save(client, faster, keep_as_draft=True)

    assert kept.json() == {
        "version": kept.json()["version"],
        "errors": [],
        "held_back": ["plans/plan.json changed"],
    }
    assert (await client.get(TASK)).json()["draft"] is True

    published = await _save(client, confirm=True)

    assert published.json()["number"] == 2
    assert (await client.get(TASK)).json()["draft"] is False


async def test_a_save_with_a_stale_token_is_a_conflict(
    client: httpx.AsyncClient, sum_task: FakeForge
) -> None:
    edit = await _edit(client, "statement.md", "Write", "One. Write")
    await _save(client, edit)

    stale = await _save(client, {**edit, "content": "Two.\n"})

    assert stale.status_code == 409
    assert stale.json()["code"] == "conflict"


async def test_a_path_named_twice_in_one_save_is_a_validation_error(
    client: httpx.AsyncClient, sum_task: FakeForge
) -> None:
    refused = await _save(
        client, _change("notes.md", "one", None), _change("notes.md", "two", None)
    )

    assert refused.status_code == 422
    assert refused.json()["code"] == "validation_error"


async def test_a_task_rollback_is_a_save(client: httpx.AsyncClient, sum_task: FakeForge) -> None:
    await publish(client)
    first = (await client.get(f"{TASK}/history", params={"path": "statement.md"})).json()
    current = await read(client, f"{TASK}/files/statement.md")

    rolled = await client.post(
        f"{TASK}/files/statement.md/rollback",
        json={"version": first[-1]["version"], "token": current["token"]},
        headers=ORIGIN,
    )

    assert rolled.status_code == 200, rolled.text
    assert rolled.json()["number"] == 2
    back = await read(client, f"{TASK}/files/statement.md")
    assert back["content"] == "Write the statement contestants read here.\n"
