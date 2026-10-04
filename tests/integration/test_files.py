"""A contest's and a task's files through the routes: a folder's entries, a
file at the latest and at an older version, the history, a write that
answers with its version at a contest and as a save at a task, a stale
token answered as a conflict, a binary file's round trip through base64, a
rollback as a new change, and the refusals a write meets: an admin-only key
changed by a manager, a `contest.yaml` that does not validate, and a path
that leaves the place.
"""

import base64
import re

import httpx
from forge.api.types import Role
from forge.testing import FakeForge

from tests.integration.conftest import CONTEST, ORIGIN, SPRING, TASK, read, sign_in_as

BINARY = b"\x89PNG\r\n\x1a\n\x00\xff\xfe"


async def _put(
    client: httpx.AsyncClient, path: str, content: str, token: str | None, **fields: object
) -> httpx.Response:
    return await client.put(
        path, json={"content": content, "token": token, **fields}, headers=ORIGIN
    )


async def test_a_tasks_top_folder_lists_its_starter_files(
    client: httpx.AsyncClient, sum_task: FakeForge
) -> None:
    listed = await client.get(f"{TASK}/tree")
    inside = await client.get(f"{TASK}/tree", params={"path": "data"})

    assert listed.status_code == 200
    entries = {entry["path"]: entry["kind"] for entry in listed.json()}
    assert entries["task.yaml"] == "file"
    assert entries["statement.md"] == "file"
    assert entries["data"] == "directory"
    assert [entry["path"] for entry in inside.json()] == ["data/testcases"]


async def test_a_contest_write_answers_its_version_and_shows_in_the_history(
    client: httpx.AsyncClient, sum_task: FakeForge
) -> None:
    before = await read(client, f"{CONTEST}/files/contest.yaml")
    changed = before["content"].replace('description: ""', "description: Our spring round")

    written = await _put(
        client, f"{CONTEST}/files/contest.yaml", changed, before["token"], message="Describe"
    )

    assert written.status_code == 200
    version = written.json()["version"]
    after = await read(client, f"{CONTEST}/files/contest.yaml")
    assert (after["content"], after["encoding"]) == (changed, "utf-8")
    assert after["token"] != before["token"]
    history = (await client.get(f"{CONTEST}/history", params={"path": "contest.yaml"})).json()
    assert (history[0]["version"], history[0]["author_id"], history[0]["message"]) == (
        version,
        7,
        "Describe",
    )
    older = await client.get(f"{CONTEST}/files/contest.yaml", params={"at": history[1]["version"]})
    assert older.json()["content"] == before["content"]


async def test_a_write_with_a_stale_token_is_a_conflict_and_writes_nothing(
    client: httpx.AsyncClient, sum_task: FakeForge
) -> None:
    before = await read(client, f"{CONTEST}/files/contest.yaml")
    first = before["content"].replace('description: ""', "description: One")
    await _put(client, f"{CONTEST}/files/contest.yaml", first, before["token"])

    stale = await _put(
        client,
        f"{CONTEST}/files/contest.yaml",
        before["content"].replace('description: ""', "description: Two"),
        before["token"],
    )

    assert stale.status_code == 409
    assert stale.json()["code"] == "conflict"
    assert (await read(client, f"{CONTEST}/files/contest.yaml"))["content"] == first


async def test_a_binary_file_goes_and_comes_back_as_base64(
    client: httpx.AsyncClient, sum_task: FakeForge
) -> None:
    encoded = base64.b64encode(BINARY).decode("ascii")

    written = await _put(client, f"{CONTEST}/files/logo.png", encoded, None, encoding="base64")

    assert written.status_code == 200
    back = await read(client, f"{CONTEST}/files/logo.png")
    assert back["encoding"] == "base64"
    assert base64.b64decode(back["content"]) == BINARY
    repo = sum_task.state.repos[("acme", "spring.contest")]
    assert repo.files["logo.png"] == BINARY


async def test_content_that_is_not_base64_is_a_validation_error(
    client: httpx.AsyncClient, sum_task: FakeForge
) -> None:
    refused = await _put(
        client, f"{CONTEST}/files/logo.png", "not base64!", None, encoding="base64"
    )

    assert refused.status_code == 422
    assert refused.json()["code"] == "validation_error"


async def test_a_rollback_writes_the_older_file_back_as_a_new_change(
    client: httpx.AsyncClient, sum_task: FakeForge
) -> None:
    first = await _put(client, f"{CONTEST}/files/notes.md", "one\n", None)
    current = await read(client, f"{CONTEST}/files/notes.md")
    await _put(client, f"{CONTEST}/files/notes.md", "two\n", current["token"])
    current = await read(client, f"{CONTEST}/files/notes.md")

    rolled = await client.post(
        f"{CONTEST}/files/notes.md/rollback",
        json={"version": first.json()["version"], "token": current["token"]},
        headers=ORIGIN,
    )

    assert rolled.status_code == 200
    assert (await read(client, f"{CONTEST}/files/notes.md"))["content"] == "one\n"
    history = (await client.get(f"{CONTEST}/history", params={"path": "notes.md"})).json()
    assert len(history) == 3
    assert history[0]["version"] == rolled.json()["version"]


async def test_a_task_write_is_a_save_and_answers_as_one(
    client: httpx.AsyncClient, sum_task: FakeForge
) -> None:
    example = await read(client, f"{TASK}/files/data/testcases/1.in")

    written = await _put(client, f"{TASK}/files/data/testcases/1.in", "1 2\n", example["token"])

    assert written.status_code == 200
    assert written.json()["number"] == 1


async def test_a_managers_change_to_an_admin_only_key_is_refused_naming_it(
    client: httpx.AsyncClient, sum_task: FakeForge
) -> None:
    await sum_task.orgs.grant_role(8, SPRING, Role.MANAGER)
    await sign_in_as(client, sum_task, 8)
    before = await read(client, f"{CONTEST}/files/contest.yaml")
    renamed = re.sub(r"(?m)^name: .*$", "name: Autumn", before["content"])
    assert renamed != before["content"]

    refused = await _put(client, f"{CONTEST}/files/contest.yaml", renamed, before["token"])

    assert refused.status_code == 403
    assert refused.json()["code"] == "admin_only"
    assert refused.json()["keys"] == ["name"]
    assert (await read(client, f"{CONTEST}/files/contest.yaml"))["content"] == before["content"]


async def test_a_contest_file_that_does_not_validate_is_refused_with_its_errors(
    client: httpx.AsyncClient, sum_task: FakeForge
) -> None:
    before = await read(client, f"{CONTEST}/files/contest.yaml")
    broken = before["content"].replace("visibility: signed-in", "visibility: everyone")

    refused = await _put(client, f"{CONTEST}/files/contest.yaml", broken, before["token"])

    assert refused.status_code == 422
    assert refused.json()["code"] == "invalid_definition"
    (error,) = refused.json()["errors"]
    assert error["path"] == "visibility"
    assert error["message"]


async def test_a_path_that_leaves_the_place_is_refused_before_the_forge_is_asked(
    client: httpx.AsyncClient, sum_task: FakeForge
) -> None:
    sum_task.reset_calls()

    read_refused = await client.get(f"{TASK}/files/%2E%2E%2Fother.task%2Ftask.yaml")
    write_refused = await _put(client, f"{TASK}/files/%2E%2E%2Fother.task%2Ftask.yaml", "x", None)

    for refused in (read_refused, write_refused):
        assert refused.status_code == 422
        assert refused.json()["code"] == "invalid_path"
        assert refused.json()["path"] == "../other.task/task.yaml"
    assert [call.operation for call in sum_task.calls if call.operation != "roles_of"] == []
