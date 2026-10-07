"""Making a task in a contest makes it with its starter files before the
request answers, and the contest lists it. A new task's head is a draft with
nothing wrong and no publication; a task in a contest that is not there is
not found. An observer of the contest reads its tasks in its order, each with
its letter, where it stands and its timeline from its entry, a failed save's
errors included; and an observer of a task reads the form of the workflow it
names, or why there is none.
"""

import httpx
from forge.testing import FakeForge, Setup

from tests.integration.conftest import CONTEST, ORG, ORIGIN, TASK, publish, read, sign_in

STANDINGS = f"{CONTEST}/organise/tasks"
FORM = f"{TASK}/workflow-form"


async def test_a_task_is_made_and_listed(
    client: httpx.AsyncClient, acme: FakeForge, held_setup: Setup
) -> None:
    await sign_in(client, acme)
    await client.post(f"{ORG}/contests", json={"name": "spring"}, headers=ORIGIN)

    made = await client.post(
        f"{CONTEST}/tasks", json={"name": "sum", "title": "Sum of Two"}, headers=ORIGIN
    )

    assert made.status_code == 201
    assert made.json() == {"name": "sum"}
    assert (await client.get(f"{CONTEST}/tasks")).json() == [{"name": "sum"}]
    settings = (await client.get(f"{TASK}/files/task.yaml")).json()
    assert 'name: "Sum of Two"' in settings["content"]


async def test_a_new_task_is_an_unsaved_draft_with_nothing_wrong(
    client: httpx.AsyncClient, sum_task: FakeForge
) -> None:
    state = await client.get(TASK)

    assert state.status_code == 200
    body = state.json()
    assert (body["latest"], body["draft"], body["errors"]) == (None, True, [])
    assert body["head"]
    assert (await client.get(f"{TASK}/publications")).json() == []


async def test_a_task_in_a_contest_that_is_not_there_is_not_found(
    client: httpx.AsyncClient, acme: FakeForge
) -> None:
    await sign_in(client, acme)

    refused = await client.post(
        f"{ORG}/contests/autumn/tasks", json={"name": "sum"}, headers=ORIGIN
    )

    assert refused.status_code == 404
    assert refused.json()["code"] == "not_found"


async def test_the_contests_tasks_stand_with_their_publication_and_timeline(
    client: httpx.AsyncClient, sum_task: FakeForge
) -> None:
    unsaved = await client.get(STANDINGS)
    await publish(client)
    published = await client.get(STANDINGS)

    assert unsaved.status_code == 200, unsaved.text
    (row,) = unsaved.json()
    assert (row["task"], row["label"]) == ({"name": "sum"}, "A")
    assert (row["state"]["latest"], row["state"]["draft"], row["state"]["errors"]) == (
        None,
        True,
        [],
    )
    assert row["timeline"] == {
        "worth": None,
        "release_at": "2026-10-03T12:00:00Z",
        "due": None,
        "late_per_day": None,
        "closes": "2026-10-03T17:00:00Z",
    }
    (row,) = published.json()
    assert (row["state"]["latest"]["number"], row["state"]["draft"]) == (1, False)
    assert row["timeline"]["worth"] == 100


async def test_a_tasks_entry_sets_its_timeline_and_a_failed_save_shows_its_errors(
    client: httpx.AsyncClient, sum_task: FakeForge
) -> None:
    await publish(client)
    settings = await read(client, f"{CONTEST}/files/contest.yaml")
    entry = "  - id: sum\n    due: 2026-10-03T16:00:00Z\n    late_per_day: 0.25\n    worth: 50\n"
    written = await client.put(
        f"{CONTEST}/files/contest.yaml",
        json={
            "content": settings["content"].replace("  - id: sum\n", entry),
            "token": settings["token"],
        },
        headers=ORIGIN,
    )
    task = await read(client, f"{TASK}/files/task.yaml")
    broken = await client.put(
        f"{TASK}/files/task.yaml",
        json={"content": task["content"] + "nonsense: [\n", "token": task["token"]},
        headers=ORIGIN,
    )

    (row,) = (await client.get(STANDINGS)).json()

    assert written.status_code == 200, written.text
    assert broken.json()["errors"], broken.text
    assert row["timeline"] == {
        "worth": 50,
        "release_at": "2026-10-03T12:00:00Z",
        "due": "2026-10-03T16:00:00Z",
        "late_per_day": 0.25,
        "closes": "2026-10-03T17:00:00Z",
    }
    assert (row["state"]["latest"]["number"], row["state"]["draft"]) == (1, True)
    assert row["state"]["errors"] == broken.json()["errors"]


async def test_the_workflow_form_gives_the_inputs_and_test_fields_the_task_names(
    client: httpx.AsyncClient, sum_task: FakeForge
) -> None:
    form = await client.get(FORM)

    assert form.status_code == 200, form.text
    body = form.json()
    assert (body["workflow"], body["problem"]) == ("unicon/classic@v2", None)
    assert [(found["id"], found["contestant"]) for found in body["inputs"]] == [
        ("submission", True),
        ("language", True),
        ("time_limit", False),
        ("memory_limit", False),
    ]
    language = body["inputs"][1]
    assert (language["type"], language["options"]) == ("enum", ["c", "cpp", "java", "python"])
    assert (language["per_test"], language["optional"]) == (False, False)
    assert body["test"] == [
        {"name": "input", "type": "file", "options": None},
        {"name": "answer", "type": "file", "options": None},
    ]


async def test_a_task_naming_no_workflow_gets_a_form_saying_why(
    client: httpx.AsyncClient, sum_task: FakeForge
) -> None:
    task = await read(client, f"{TASK}/files/task.yaml")
    await client.put(
        f"{TASK}/files/task.yaml",
        json={
            "content": task["content"].replace("workflow: unicon/classic@v2\n", ""),
            "token": task["token"],
        },
        headers=ORIGIN,
    )

    form = await client.get(FORM)

    assert form.status_code == 200, form.text
    assert (form.json()["workflow"], form.json()["inputs"], form.json()["test"]) == (None, [], [])
    assert form.json()["problem"]


async def test_a_contestant_reads_neither_the_standings_nor_the_form(
    client: httpx.AsyncClient, entered: FakeForge
) -> None:
    for refused in (await client.get(STANDINGS), await client.get(FORM)):
        assert (refused.status_code, refused.json()["code"]) == (403, "forbidden")
