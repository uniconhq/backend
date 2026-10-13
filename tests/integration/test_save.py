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


EFFECT = ("results_change", "summary", "runs_again", "scores", "reading")
"""What a save does, as the question before it and the answer after give it."""


def _change(path: str, content: str, token: str | None) -> dict[str, Any]:
    return {"path": path, "encoding": "utf-8", "content": content, "token": token}


async def _save(
    client: httpx.AsyncClient, *changes: dict[str, Any], **options: bool | str
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
    assert first["notes"] == []
    assert first["effect"]["scores"] == [
        "Points: main is worth up to 100.",
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
    # Each value its workflow reports, with the words a page names it by.
    assert published[0]["meanings"] == [
        {"name": "time_ms", "title": "Run time", "unit": "ms", "better": "lower"},
        {"name": "memory_kb", "title": "Memory used", "unit": "KB", "better": "lower"},
        {"name": "log", "title": "Compile log", "unit": None, "better": None},
    ]
    assert state["latest"]["meanings"] == published[1]["meanings"]


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
    assert {key: asked.json()[key] for key in EFFECT} == {
        "results_change": False,
        "summary": "Nobody's result changes.",
        "runs_again": [
            "No submission runs again: there are none yet.",
            "The way the task grades changed.",
        ],
        "scores": ["The leaderboard Standings is counted again."],
        "reading": ["Nothing entrants read changes."],
    }
    assert len((await client.get(f"{TASK}/publications")).json()) == 1

    confirmed = await _save(client, faster, confirm=True, asked=asked.json()["asked"])

    assert confirmed.status_code == 200
    assert (confirmed.json()["number"], confirmed.json()["grading_changed"]) == (2, True)
    assert confirmed.json()["changes"] == ["The way the task grades changed."]
    assert confirmed.json()["effect"] == {key: asked.json()[key] for key in EFFECT}


async def test_a_confirmation_asked_about_another_head_is_asked_again(
    client: httpx.AsyncClient, running: FakeForge
) -> None:
    statement = await _edit(client, "statement.md", "Add", "Now add")
    asked = await _save(client, statement)
    faster = await _edit(client, "task.yaml", "time_limit: 2", "time_limit: 1")
    assert (await _save(client, faster, keep_as_draft=True)).status_code == 200

    again = await _save(client, statement, confirm=True, asked=asked.json()["asked"])

    assert again.status_code == 409
    assert again.json()["changes"] == ["The way the task grades changed."]
    confirmed = await _save(client, statement, confirm=True, asked=again.json()["asked"])
    assert (confirmed.status_code, confirmed.json()["grading_changed"]) == (200, True)


async def _written_as_asked(
    client: httpx.AsyncClient, method: str, url: str, body: dict[str, Any]
) -> httpx.Response:
    """The write sent once, asked about while the contest runs, then sent
    again with the confirmation and what it was asked about."""
    asked = await client.request(method, url, json=body, headers=ORIGIN)
    assert (asked.status_code, asked.json()["code"]) == (409, "confirmation_required")
    confirmed = {**body, "confirm": True, "asked": asked.json()["asked"]}
    return await client.request(method, url, json=confirmed, headers=ORIGIN)


async def test_a_file_written_or_rolled_back_while_the_contest_runs_asks_and_is_confirmed(
    client: httpx.AsyncClient, running: FakeForge
) -> None:
    statement = await read(client, f"{TASK}/files/statement.md")
    [*_, first] = (await client.get(f"{TASK}/history", params={"path": "statement.md"})).json()

    written = await _written_as_asked(
        client,
        "PUT",
        f"{TASK}/files/statement.md",
        {"encoding": "utf-8", "content": "Now add.\n", "token": statement["token"]},
    )
    assert (written.status_code, written.json()["number"]) == (200, 2), written.text
    current = await read(client, f"{TASK}/files/statement.md")
    rolled = await _written_as_asked(
        client,
        "POST",
        f"{TASK}/files/statement.md/rollback",
        {"version": first["version"], "token": current["token"]},
    )
    assert (rolled.status_code, rolled.json()["number"]) == (200, 3), rolled.text


async def test_a_change_to_the_statement_or_the_points_while_the_contest_runs_asks_first(
    client: httpx.AsyncClient, running: FakeForge
) -> None:
    statement = await _edit(client, "statement.md", "Add", "Now add")

    asked = await _save(client, statement)

    assert asked.status_code == 409
    assert (asked.json()["changes"], asked.json()["reading"]) == (
        [],
        ["The statement changes."],
    )
    assert asked.json()["runs_again"] == [
        "No submission runs again: the tests and how they run are the same."
    ]
    points = await _edit(client, "task.yaml", "{each: 100}", "{each: 110}")
    assert (await _save(client, points)).json()["scores"] == [
        "Points: main is now worth up to 110 (was 100).",
        "Every result is scored again, and the leaderboard Standings with it.",
    ]
    # Saved as the latest publication holds it, nothing new: no question.
    same = await _edit(client, "task.yaml", "{each: 100}", "{each: 100}")
    assert (await _save(client, same)).status_code == 200


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
        "The answer of test 2 in the group main was removed.",
        "The input of test 2 in the group main was removed.",
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
