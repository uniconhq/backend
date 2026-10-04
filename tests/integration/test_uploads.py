"""A person's upload through the routes: a slot naming where to send the
file, the bytes through the upload door, and the completion once the forge
holds them. A file the forge already holds needs no upload at all.

The door is what the proxy asks before it reads a body. It answers 204 and
two headers for the owner's own waiting upload of exactly the length the
request carries; everything else is 403 with no reason, so nothing is
learned from which refusal it was. It is left out of the OpenAPI document,
because its answer carries a credential.

Also here: the refusals a slot meets, each with its code; someone else's
upload is no such upload; and every route needs a session.
"""

import hashlib
import uuid
from datetime import timedelta

import httpx
import pytest
from fastapi import FastAPI
from forge.testing import FakeClock, FakeForge, Setup

from tests.integration.conftest import (
    ORIGIN,
    TASK,
    enter,
    publish,
    run_contest,
    sign_in_as,
    upload,
)

SOURCE = b"print(sum(map(int, input().split())))\n"
MIB = 1024 * 1024
UPLOADS = f"{TASK}/uploads"
DOOR = "/-/uploads/door"
DIGEST = hashlib.sha256(SOURCE).hexdigest()


def _ask(size: int, digest: str = DIGEST, **fields: object) -> dict[str, object]:
    return {
        "input": "submission",
        "filename": "main.py",
        "size": size,
        "sha256": digest,
        **fields,
    }


async def _door(client: httpx.AsyncClient, upload_id: str, length: int) -> httpx.Response:
    """What the proxy asks, with the headers it sends."""
    return await client.get(
        DOOR,
        headers={"X-Original-URI": f"/-/uploads/{upload_id}", "X-Upload-Length": str(length)},
    )


async def test_a_file_goes_through_the_door_and_is_verified_by_the_forge(
    client: httpx.AsyncClient, entered: FakeForge
) -> None:
    slot = await client.post(UPLOADS, json=_ask(len(SOURCE)), headers=ORIGIN)
    body = slot.json()
    door = await _door(client, body["id"], len(SOURCE))
    entered.uploads.send(
        door.headers["X-Forge-Path"], door.headers["X-Forge-Authorization"], SOURCE
    )
    completed = await client.post(f"{UPLOADS}/{body['id']}/complete", headers=ORIGIN)
    again = await client.post(f"{UPLOADS}/{body['id']}/complete", headers=ORIGIN)

    assert slot.status_code == 201, slot.text
    assert sorted(body) == ["expires_at", "id", "ready", "url"]
    assert (body["url"], body["ready"]) == (f"/-/uploads/{body['id']}", False)
    assert door.status_code == 204, door.text
    assert completed.status_code == 200, completed.text
    assert completed.json() == {
        "id": body["id"],
        "input": "submission",
        "filename": "main.py",
        "content_type": None,
        "size": len(SOURCE),
        "sha256": DIGEST,
        "status": "verified",
    }
    assert again.json() == completed.json()


async def test_a_file_the_forge_already_holds_is_ready_with_nothing_to_send(
    client: httpx.AsyncClient, entered: FakeForge
) -> None:
    await upload(client, entered, SOURCE)

    slot = await client.post(UPLOADS, json=_ask(len(SOURCE)), headers=ORIGIN)
    body = slot.json()

    assert (body["ready"], body["url"]) is not None and body["ready"] is True
    assert body["url"] is None
    completed = await client.post(f"{UPLOADS}/{body['id']}/complete", headers=ORIGIN)
    assert completed.json()["status"] == "verified"


async def test_the_door_answers_where_the_bytes_go_and_what_to_present(
    client: httpx.AsyncClient, entered: FakeForge
) -> None:
    body = (await client.post(UPLOADS, json=_ask(len(SOURCE)), headers=ORIGIN)).json()

    door = await _door(client, body["id"], len(SOURCE))

    # The path names the repository, the digest and the length; nothing of
    # the browser's request builds it.
    assert DIGEST in door.headers["X-Forge-Path"]
    assert str(len(SOURCE)) in door.headers["X-Forge-Path"]
    assert door.headers["X-Forge-Authorization"].startswith("Basic ")
    assert door.content == b""


async def test_the_door_refuses_everything_that_is_not_this_upload_now(
    client: httpx.AsyncClient, entered: FakeForge, held_setup: Setup
) -> None:
    body = (await client.post(UPLOADS, json=_ask(len(SOURCE)), headers=ORIGIN)).json()

    wrong_length = await _door(client, body["id"], len(SOURCE) + 1)
    no_length = await client.get(DOOR, headers={"X-Original-URI": f"/-/uploads/{body['id']}"})
    not_an_id = await client.get(
        DOOR, headers={"X-Original-URI": "/-/uploads/nope", "X-Upload-Length": "1"}
    )
    unknown = await _door(client, str(uuid.uuid4()), len(SOURCE))
    await enter(client, entered, held_setup, 8)
    someone_else = await _door(client, body["id"], len(SOURCE))

    answers = [wrong_length, no_length, not_an_id, unknown, someone_else]
    assert [answer.status_code for answer in answers] == [403] * 5
    # Every refusal says the same thing, and none of them says which it was.
    assert {answer.json()["code"] for answer in answers} == {"forbidden"}
    assert {answer.json()["detail"] for answer in answers} == {"That upload cannot be sent."}
    assert all("X-Forge-Authorization" not in answer.headers for answer in answers)


async def test_the_door_will_not_open_twice_for_an_upload_that_arrived(
    client: httpx.AsyncClient, entered: FakeForge
) -> None:
    made = await upload(client, entered, SOURCE)

    again = await _door(client, made["id"], len(SOURCE))

    assert again.status_code == 403


async def test_the_door_needs_a_session(client: httpx.AsyncClient, entered: FakeForge) -> None:
    body = (await client.post(UPLOADS, json=_ask(len(SOURCE)), headers=ORIGIN)).json()
    client.cookies.clear()

    refused = await _door(client, body["id"], len(SOURCE))

    assert refused.status_code == 401
    assert "X-Forge-Authorization" not in refused.headers


def test_the_door_is_not_in_the_openapi_document(app: FastAPI) -> None:
    # Its answer carries a credential, so it is not something the document
    # advertises, and the proxy never routes it from outside.
    assert not any("/-/uploads" in path for path in app.openapi()["paths"])


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
    made = await upload(client, entered, SOURCE)
    await enter(client, entered, held_setup, 8)

    theirs = await client.post(f"{UPLOADS}/{made['id']}/complete", headers=ORIGIN)
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
        ({"sha256": "not a digest"}, 422, "invalid_inputs"),
        ({"sha256": DIGEST.upper()}, 422, "invalid_inputs"),
    ],
    ids=[
        "too large",
        "no such input",
        "a folder in the name",
        "a negative size",
        "a digest that is not one",
        "a digest in capitals",
    ],
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


async def test_a_person_who_may_not_submit_is_refused_a_slot(
    client: httpx.AsyncClient, world: FakeForge, held_setup: Setup, clock: FakeClock
) -> None:
    await run_contest(client, visibility="public")
    await publish(client)
    await sign_in_as(client, world, 20)
    unregistered = await client.post(UPLOADS, json=_ask(1), headers=ORIGIN)
    await enter(client, world, held_setup, 8)
    clock.advance(timedelta(hours=4))
    ended = await client.post(UPLOADS, json=_ask(1), headers=ORIGIN)

    assert (unregistered.status_code, unregistered.json()["code"]) == (403, "not_approved")
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
