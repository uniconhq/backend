"""A contestant's upload through the routes: a slot for one request whose
form the store takes, completed as verified with its size and digest and the
same when asked again; a larger file in parts, each sent to its own URL and
named with its `ETag` at the completion; a file of another size rejected;
and the refusals a slot meets, each with its code: a file too large for the
task, an input the task has no file for, a person who is not an approved
contestant, one whose workspace is still being made, and a task past its
end. Someone else's upload is no such upload, and every route needs a
session.
"""

import hashlib
import uuid
from datetime import timedelta

import httpx
import pytest
from forge.api import contests
from forge.testing import FakeClock, FakeForge, Setup, register_contestant

from tests.integration.conftest import (
    ORIGIN,
    SPRING,
    TASK,
    edit_task,
    enter,
    publish,
    run_contest,
    sign_in_as,
    upload,
)

SOURCE = b"print(sum(map(int, input().split())))\n"
MIB = 1024 * 1024
UPLOADS = f"{TASK}/uploads"


def _ask(size: int, **fields: object) -> dict[str, object]:
    return {"input": "submission", "filename": "main.py", "size": size, **fields}


async def test_a_file_sent_in_one_request_is_verified_with_its_size_and_digest(
    client: httpx.AsyncClient, entered: FakeForge
) -> None:
    slot = await client.post(UPLOADS, json=_ask(len(SOURCE)), headers=ORIGIN)
    body = slot.json()
    entered.objects.post(body["fields"], SOURCE)
    completed = await client.post(f"{UPLOADS}/{body['id']}/complete", headers=ORIGIN)
    again = await client.post(f"{UPLOADS}/{body['id']}/complete", json={}, headers=ORIGIN)

    assert slot.status_code == 201, slot.text
    assert sorted(body) == ["expires_at", "fields", "id", "method", "url"]
    assert body["method"] == "post"
    assert body["fields"]["key"] == f"uploads/{body['id']}"
    assert completed.status_code == 200, completed.text
    assert completed.json() == {
        "id": body["id"],
        "input": "submission",
        "filename": "main.py",
        "content_type": None,
        "declared_size": len(SOURCE),
        "size": len(SOURCE),
        "sha256": hashlib.sha256(SOURCE).hexdigest(),
        "status": "verified",
    }
    assert again.json() == completed.json()


async def test_a_larger_file_is_sent_in_parts_and_named_part_by_part(
    client: httpx.AsyncClient, entered: FakeForge
) -> None:
    await sign_in_as(client, entered, 7)
    await edit_task(client, "max_size: 10MB", "max_size: 64MB")
    await sign_in_as(client, entered, 20)
    content = b"x" * (16 * MIB + 1)

    slot = await client.post(UPLOADS, json=_ask(len(content)), headers=ORIGIN)
    body = slot.json()
    size = body["part_size"]
    etags = [
        entered.objects.put_part(part["url"], content[index * size : (index + 1) * size])
        for index, part in enumerate(body["parts"])
    ]
    parts = [
        {"number": part["number"], "etag": etag}
        for part, etag in zip(body["parts"], etags, strict=True)
    ]
    missing = await client.post(
        f"{UPLOADS}/{body['id']}/complete", json={"parts": parts[:-1]}, headers=ORIGIN
    )
    completed = await client.post(
        f"{UPLOADS}/{body['id']}/complete", json={"parts": parts}, headers=ORIGIN
    )

    assert slot.status_code == 201, slot.text
    assert sorted(body) == ["expires_at", "id", "method", "part_size", "parts"]
    assert (body["method"], size) == ("multipart", 8 * MIB)
    assert [part["number"] for part in body["parts"]] == [1, 2, 3]
    assert (missing.status_code, missing.json()["code"]) == (409, "upload_not_ready")
    assert missing.json()["uploads"] == [body["id"]]
    assert (completed.json()["status"], completed.json()["size"]) == ("verified", len(content))


async def test_a_file_of_another_size_than_declared_is_rejected(
    client: httpx.AsyncClient, entered: FakeForge
) -> None:
    slot = (await client.post(UPLOADS, json=_ask(len(SOURCE) + 1), headers=ORIGIN)).json()
    entered.objects.post(slot["fields"], SOURCE)

    completed = await client.post(f"{UPLOADS}/{slot['id']}/complete", headers=ORIGIN)

    assert (completed.json()["status"], completed.json()["size"]) == ("rejected", len(SOURCE))


async def test_bytes_that_have_not_arrived_are_not_ready(
    client: httpx.AsyncClient, entered: FakeForge
) -> None:
    slot = (await client.post(UPLOADS, json=_ask(len(SOURCE)), headers=ORIGIN)).json()

    early = await client.post(f"{UPLOADS}/{slot['id']}/complete", headers=ORIGIN)

    assert (early.status_code, early.json()["code"]) == (409, "upload_not_ready")
    assert early.json()["uploads"] == [slot["id"]]


async def test_someone_elses_upload_is_no_such_upload(
    client: httpx.AsyncClient, entered: FakeForge, held_setup: Setup
) -> None:
    slot = (await client.post(UPLOADS, json=_ask(len(SOURCE)), headers=ORIGIN)).json()
    entered.objects.post(slot["fields"], SOURCE)
    await enter(client, entered, held_setup, 8)

    theirs = await client.post(f"{UPLOADS}/{slot['id']}/complete", headers=ORIGIN)
    nobodys = await client.post(f"{UPLOADS}/{uuid.uuid4()}/complete", headers=ORIGIN)

    assert (theirs.status_code, theirs.json()["code"]) == (404, "not_found")
    assert theirs.json() == nobodys.json()


@pytest.mark.parametrize(
    ("fields", "status", "code"),
    [
        ({"size": 10 * MIB + 1}, 413, "too_large"),
        ({"input": "nothing"}, 422, "invalid_inputs"),
        ({"filename": "../main.py"}, 422, "invalid_inputs"),
        ({"size": -1}, 422, "invalid_inputs"),
    ],
    ids=["too large", "no such input", "a folder in the name", "a negative size"],
)
async def test_a_slot_the_task_does_not_take_is_refused_with_its_code(
    client: httpx.AsyncClient,
    entered: FakeForge,
    fields: dict[str, object],
    status: int,
    code: str,
) -> None:
    refused = await client.post(UPLOADS, json=_ask(len(SOURCE)) | fields, headers=ORIGIN)

    assert (refused.status_code, refused.json()["code"]) == (status, code)
    if code == "too_large":
        assert (refused.json()["limit"], refused.json()["input"]) == (10 * MIB, None)
    else:
        assert refused.json()["errors"][0]["input"] == fields.get("input", "submission")


async def test_a_person_who_may_not_submit_is_refused_a_slot(
    client: httpx.AsyncClient, world: FakeForge, held_setup: Setup, clock: FakeClock
) -> None:
    await run_contest(client, visibility="public")
    await publish(client)
    await sign_in_as(client, world, 20)
    unregistered = await client.post(UPLOADS, json=_ask(1), headers=ORIGIN)
    await register_contestant(held_setup, contests.contest_id_of(SPRING), 20)
    preparing = await client.post(UPLOADS, json=_ask(1), headers=ORIGIN)
    await enter(client, world, held_setup, 8)
    clock.advance(timedelta(hours=4))
    ended = await client.post(UPLOADS, json=_ask(1), headers=ORIGIN)

    assert (unregistered.status_code, unregistered.json()["code"]) == (403, "not_approved")
    assert (preparing.status_code, preparing.json()["code"]) == (409, "workspace_not_ready")
    assert (ended.status_code, ended.json()["code"]) == (403, "task_closed")
    assert ended.json()["reason"] == "ended"


async def test_the_upload_routes_need_a_session(
    client: httpx.AsyncClient, entered: FakeForge
) -> None:
    made = await upload(client, entered, SOURCE)
    client.cookies.clear()

    answers = [
        await client.post(UPLOADS, json=_ask(1), headers=ORIGIN),
        await client.post(f"{UPLOADS}/{made['id']}/complete", headers=ORIGIN),
    ]

    assert [(answer.status_code, answer.json()["code"]) for answer in answers] == [
        (401, "unauthenticated")
    ] * 2
