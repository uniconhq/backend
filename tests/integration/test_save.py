"""The save, which is how a task is published, through the routes: the whole
organiser path from an org through the poller to a publication number; a
save of the statement that does not change how the task grades; a save
that does not check, kept as a draft with its errors, which the task then
shows; the refusals, a path inside `plans/`, a manager's change to an
admin-only file and a grading change while the contest runs, which the same
save confirmed publishes; a change kept as a draft and published by an
empty confirmed save; a stale token answered as a conflict; and a removal,
a path with its token and `remove`, which takes a test out or replaces it
by one with other entry names, is checked as any other state, and is
refused as an edit is.
"""

import uuid
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
        "message": "main holds tests but is not one of the task's test groups. Add a test group "
        "called main, or move its tests.",
    },
    {
        "path": "test_groups.hidden",
        "message": "The test group hidden has no tests. Add a test to it.",
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
        "The most points each test group gives: main 100.",
        "sum shows its hidden results at 2026-10-03T17:00:00+00:00.",
        "sum now counts on the leaderboard Standings.",
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
    assert asked.json()["changes"] == ["The way the task grades changed."]
    assert asked.json()["regrades"] == 0
    assert len((await client.get(f"{TASK}/publications")).json()) == 1

    confirmed = await _save(client, faster, confirm=True)

    assert confirmed.status_code == 200
    assert (confirmed.json()["number"], confirmed.json()["grading_changed"]) == (2, True)
    assert confirmed.json()["changes"] == ["The way the task grades changed."]


async def test_a_change_kept_as_a_draft_is_published_by_an_empty_confirmed_save(
    client: httpx.AsyncClient, running: FakeForge
) -> None:
    faster = await _edit(client, "task.yaml", "time_limit: 2", "time_limit: 1")

    kept = await _save(client, faster, keep_as_draft=True)

    assert kept.json() == {
        "version": kept.json()["version"],
        "errors": [],
        "held_back": ["The way the task grades changed."],
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


def _removal(path: str, token: str | None) -> dict[str, Any]:
    return {"path": path, "token": token, "remove": True}


async def _token(client: httpx.AsyncClient, path: str) -> str:
    token: str = (await read(client, f"{TASK}/files/{path}"))["token"]
    return token


async def test_a_save_removes_a_test_and_its_publication_names_the_removal(
    client: httpx.AsyncClient, sum_task: FakeForge
) -> None:
    await publish(client)
    added = await _save(
        client,
        _change("tests/main/2/input", "1 1\n", None),
        _change("tests/main/2/answer", "2\n", None),
    )
    assert added.json()["number"] == 2, added.text

    removed = await _save(
        client,
        _removal("tests/main/2/input", await _token(client, "tests/main/2/input")),
        _removal("tests/main/2/answer", await _token(client, "tests/main/2/answer")),
    )

    assert removed.status_code == 200, removed.text
    assert (removed.json()["number"], removed.json()["grading_changed"]) == (3, True)
    assert removed.json()["changes"] == [
        "The way the task grades changed.",
        "The file tests/main/2/answer was removed.",
        "The file tests/main/2/input was removed.",
    ]
    gone = await client.get(f"{TASK}/files/tests/main/2/input")
    assert gone.status_code == 404


async def test_a_test_is_replaced_by_one_with_other_entry_names(
    client: httpx.AsyncClient, sum_task: FakeForge
) -> None:
    await publish(client)

    replaced = await _save(
        client,
        _removal("tests/main/1/input", await _token(client, "tests/main/1/input")),
        _removal("tests/main/1/answer", await _token(client, "tests/main/1/answer")),
        _change("tests/main/1/input.txt", "4 5\n", None),
        _change("tests/main/1/answer.txt", "9\n", None),
    )

    assert replaced.status_code == 200, replaced.text
    assert replaced.json()["number"] == 2


async def test_removing_every_test_keeps_the_save_as_a_draft(
    client: httpx.AsyncClient, sum_task: FakeForge
) -> None:
    await publish(client)

    kept = await _save(
        client,
        _removal("tests/main/1/input", await _token(client, "tests/main/1/input")),
        _removal("tests/main/1/answer", await _token(client, "tests/main/1/answer")),
    )

    assert kept.status_code == 200, kept.text
    assert kept.json()["errors"] == [
        {
            "path": "test_groups",
            "message": "The task has no tests yet. Add a test to each test group.",
        }
    ]
    assert len((await client.get(f"{TASK}/publications")).json()) == 1


async def test_a_removal_with_a_stale_token_is_a_conflict(
    client: httpx.AsyncClient, sum_task: FakeForge
) -> None:
    await _save(client, _change("public/hint.txt", "One.\n", None))
    stale = _removal("public/hint.txt", await _token(client, "public/hint.txt"))
    await _save(client, await _edit(client, "public/hint.txt", "One.", "Two."))

    refused = await _save(client, stale)

    assert refused.status_code == 409
    assert refused.json()["code"] == "conflict"
    assert (await read(client, f"{TASK}/files/public/hint.txt"))["content"] == "Two.\n"


async def test_a_managers_removal_of_the_statement_is_refused(
    client: httpx.AsyncClient, sum_task: FakeForge
) -> None:
    token = await _token(client, "statement.md")
    await sum_task.orgs.grant_role(8, SUM, Role.MANAGER)
    await sign_in_as(client, sum_task, 8)

    refused = await _save(client, _removal("statement.md", token))

    assert refused.status_code == 403
    assert (refused.json()["code"], refused.json()["keys"]) == ("admin_only", ["statement.md"])


@pytest.mark.parametrize(
    "change",
    [
        {"path": "public/a.txt", "token": None, "remove": True},
        {"path": "public/a.txt", "token": "abc", "remove": True, "content": "x"},
        {"path": "public/a.txt", "token": "abc", "remove": True, "upload": str(uuid.uuid4())},
        {"path": "public/a.txt", "token": "abc"},
    ],
    ids=["no-token", "with-content", "with-upload", "nothing"],
)
async def test_a_removal_is_a_path_and_its_token_and_nothing_else(
    client: httpx.AsyncClient, sum_task: FakeForge, change: dict[str, Any]
) -> None:
    refused = await _save(client, change)

    assert refused.status_code == 422
    assert refused.json()["code"] == "validation_error"
    assert sum_task.calls_to("save_files") == []


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
    assert back["content"] == "Write the statement entrants read here.\n"
