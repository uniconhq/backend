"""An organiser's file into a task through the routes: a slot naming the path
it is for, the bytes through the same door a contestant's go through, the
same completion, and a save, or a write of the one file, naming the upload in
place of content, which writes the pointer to it. The file is then listed and
read as an upload, with the size and digest of what it holds, and a typed
file is not.

Also here: a save naming an upload that is not the caller's for that path,
or whose bytes have not arrived, is refused with the contestant's codes; a
change gives content or an upload, never both or neither; a contest's file
takes no upload; and only a manager of the task gets a slot.
"""

import hashlib
import uuid
from typing import Any

import httpx
from forge.api.types import Role
from forge.testing import FakeForge

from tests.integration.conftest import CONTEST, ORIGIN, SUM, TASK, read, sign_in_as

DATA = b"a dataset, pretend it is large\n" * 32
DIGEST = hashlib.sha256(DATA).hexdigest()
PATH = "data/weights.bin"
SLOTS = f"{TASK}/organise/uploads"


async def _slot(
    client: httpx.AsyncClient, path: str = PATH, content: bytes = DATA
) -> dict[str, Any]:
    slot = await client.post(
        SLOTS,
        json={"path": path, "size": len(content), "sha256": hashlib.sha256(content).hexdigest()},
        headers=ORIGIN,
    )
    assert slot.status_code == 201, slot.text
    body: dict[str, Any] = slot.json()
    return body


async def _uploaded(
    client: httpx.AsyncClient, forge: FakeForge, path: str = PATH, content: bytes = DATA
) -> dict[str, Any]:
    """A file uploaded into the task the way the organiser's browser does it:
    the slot, the bytes through the door, and the completion. Returns the
    upload.
    """
    slot = await _slot(client, path, content)
    door = await client.get(
        "/-/uploads/door",
        headers={
            "X-Original-URI": f"/-/uploads/{slot['id']}",
            "X-Upload-Length": str(len(content)),
        },
    )
    assert door.status_code == 204, door.text
    forge.uploads.send(door.headers["X-Forge-Path"], door.headers["X-Forge-Authorization"], content)
    completed = await client.post(f"{TASK}/uploads/{slot['id']}/complete", headers=ORIGIN)
    assert completed.status_code == 200, completed.text
    upload: dict[str, Any] = completed.json()
    return upload


async def _save(client: httpx.AsyncClient, *changes: dict[str, Any]) -> httpx.Response:
    return await client.post(f"{TASK}/save", json={"changes": list(changes)}, headers=ORIGIN)


async def test_an_organisers_upload_is_saved_into_the_task_and_read_as_an_upload(
    client: httpx.AsyncClient, sum_task: FakeForge
) -> None:
    upload = await _uploaded(client, sum_task)

    saved = await _save(client, {"path": PATH, "upload": upload["id"], "token": None})
    listed = await client.get(f"{TASK}/tree", params={"path": "data"})
    file = await read(client, f"{TASK}/files/{PATH}")
    typed = await read(client, f"{TASK}/files/task.yaml")
    top = await client.get(f"{TASK}/tree")

    assert (upload["input"], upload["filename"], upload["status"]) == (
        "",
        "weights.bin",
        "verified",
    )
    assert saved.status_code == 200, saved.text
    assert [(entry["path"], entry["upload"]) for entry in listed.json()] == [
        (PATH, {"size": len(DATA), "digest": DIGEST})
    ]
    assert file["upload"] == {"size": len(DATA), "digest": DIGEST}
    assert DIGEST in file["content"]
    assert typed["upload"] is None
    assert all(entry["upload"] is None for entry in top.json())


async def test_a_write_of_one_file_takes_an_upload_in_place_of_content(
    client: httpx.AsyncClient, sum_task: FakeForge
) -> None:
    first = await _uploaded(client, sum_task)
    await _save(client, {"path": PATH, "upload": first["id"], "token": None})
    current = await read(client, f"{TASK}/files/{PATH}")
    again = await _uploaded(client, sum_task, content=DATA + b"one more row\n")

    written = await client.put(
        f"{TASK}/files/{PATH}",
        json={"upload": again["id"], "token": current["token"], "message": "Again"},
        headers=ORIGIN,
    )
    history = await client.get(f"{TASK}/history", params={"path": PATH})

    assert written.status_code == 200, written.text
    assert "number" in written.json() or "version" in written.json()
    assert len(history.json()) == 2
    assert (await read(client, f"{TASK}/files/{PATH}"))["upload"]["size"] == len(DATA) + 13


async def test_a_save_naming_an_upload_that_is_not_for_it_is_refused_at_its_path(
    client: httpx.AsyncClient, sum_task: FakeForge
) -> None:
    upload = await _uploaded(client, sum_task)

    nobodys = await _save(client, {"path": PATH, "upload": str(uuid.uuid4()), "token": None})
    elsewhere = await _save(
        client, {"path": "data/other.bin", "upload": upload["id"], "token": None}
    )

    for refused in (nobodys, elsewhere):
        assert (refused.status_code, refused.json()["code"]) == (422, "invalid_inputs")
    assert [error["input"] for error in nobodys.json()["errors"]] == [PATH]
    assert [error["input"] for error in elsewhere.json()["errors"]] == ["data/other.bin"]
    assert (await client.get(f"{TASK}/tree", params={"path": "data"})).status_code == 404


async def test_an_upload_whose_bytes_have_not_arrived_is_not_ready(
    client: httpx.AsyncClient, sum_task: FakeForge
) -> None:
    slot = await _slot(client)

    completed = await client.post(f"{TASK}/uploads/{slot['id']}/complete", headers=ORIGIN)
    saved = await _save(client, {"path": PATH, "upload": slot["id"], "token": None})

    assert (completed.status_code, completed.json()["code"]) == (409, "upload_not_ready")
    assert (saved.status_code, saved.json()["code"]) == (409, "upload_not_ready")
    assert saved.json()["uploads"] == [slot["id"]]


async def test_a_change_gives_content_or_an_upload_and_never_both(
    client: httpx.AsyncClient, sum_task: FakeForge
) -> None:
    upload = str(uuid.uuid4())

    both = await _save(client, {"path": PATH, "content": "x", "upload": upload, "token": None})
    neither = await _save(client, {"path": PATH, "token": None})
    written = await client.put(
        f"{TASK}/files/{PATH}",
        json={"content": "x", "upload": upload, "token": None},
        headers=ORIGIN,
    )

    for refused in (both, neither, written):
        assert (refused.status_code, refused.json()["code"]) == (422, "validation_error")


async def test_a_contests_file_takes_no_upload(
    client: httpx.AsyncClient, sum_task: FakeForge
) -> None:
    upload = await _uploaded(client, sum_task)

    written = await client.put(
        f"{CONTEST}/files/data.bin", json={"upload": upload["id"], "token": None}, headers=ORIGIN
    )

    assert (written.status_code, written.json()["code"]) == (422, "validation_error")


async def test_a_slot_for_a_path_that_leaves_the_task_or_a_bad_digest_is_refused(
    client: httpx.AsyncClient, sum_task: FakeForge
) -> None:
    leaves = await client.post(
        SLOTS, json={"path": "../x.bin", "size": 1, "sha256": DIGEST}, headers=ORIGIN
    )
    bad = await client.post(
        SLOTS, json={"path": PATH, "size": 1, "sha256": "not-a-digest"}, headers=ORIGIN
    )

    assert (leaves.status_code, leaves.json()["code"]) == (422, "invalid_path")
    assert (bad.status_code, bad.json()["code"]) == (422, "invalid_inputs")


async def test_an_observer_gets_no_slot_and_saves_no_upload(
    client: httpx.AsyncClient, world: FakeForge
) -> None:
    await world.orgs.grant_role(20, SUM, Role.OBSERVER)
    await sign_in_as(client, world, 20)

    refused = await client.post(
        SLOTS, json={"path": PATH, "size": len(DATA), "sha256": DIGEST}, headers=ORIGIN
    )
    saved = await _save(client, {"path": PATH, "upload": str(uuid.uuid4()), "token": None})

    assert (refused.status_code, refused.json()["code"]) == (403, "forbidden")
    assert (saved.status_code, saved.json()["code"]) == (403, "forbidden")


async def test_the_organisers_slot_needs_a_session(
    client: httpx.AsyncClient, sum_task: FakeForge
) -> None:
    client.cookies.clear()

    refused = await client.post(
        SLOTS, json={"path": PATH, "size": len(DATA), "sha256": DIGEST}, headers=ORIGIN
    )

    assert (refused.status_code, refused.json()["code"]) == (401, "unauthenticated")
