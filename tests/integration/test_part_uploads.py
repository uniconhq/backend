"""Owner-bound multipart routes feed the existing task and workflow saves."""

import hashlib

import httpx
import pytest
from forge.testing import FakeForge, Setup

from tests.integration.conftest import ORIGIN, TASK, run_contest, sign_in_as


async def _sent(client: httpx.AsyncClient, forge: FakeForge, base: str, body: bytes) -> str:
    started = await client.post(
        base,
        json={"path": "data.bin", "size": len(body), "sha256": hashlib.sha256(body).hexdigest()},
        headers=ORIGIN,
    )
    assert started.status_code == 201, started.text
    upload = started.json()["id"]
    assert isinstance(upload, str)
    signed = await client.post(f"{base}/{upload}/sign", json={"numbers": [1]}, headers=ORIGIN)
    assert signed.status_code == 200, signed.text
    forge.objects.put(signed.json()["1"], body)
    current = await client.get(f"{base}/{upload}")
    assert [part["number"] for part in current.json()["parts"]] == [1]
    assert [row["id"] for row in (await client.get(base)).json()] == [upload]
    part = current.json()["parts"][0]
    finished = await client.post(
        f"{base}/{upload}/finish",
        json={"parts": [{"number": part["number"], "etag": part["etag"]}]},
        headers=ORIGIN,
    )
    assert finished.status_code == 200, finished.text
    assert finished.json()["status"] == "finishing"
    return upload


async def test_task_parts_are_stored_before_the_existing_file_save_uses_them(
    client: httpx.AsyncClient, world: FakeForge, held_setup: Setup
) -> None:
    await run_contest(client, visibility="everyone")
    base = f"{TASK}/organise/part-uploads"
    upload = await _sent(client, world, base, b"task data")
    await held_setup.settle()
    assert (await client.get(f"{base}/{upload}")).json()["status"] == "stored"
    saved = await client.put(
        f"{TASK}/files/data.bin",
        json={"upload": upload, "token": None, "confirm": True},
        headers=ORIGIN,
    )
    assert saved.status_code == 200, saved.text
    tree = (await client.get(f"{TASK}/tree")).json()
    assert any(row["path"] == "data.bin" and row["upload"]["size"] == 9 for row in tree)
    assert world.objects.uploads == {}


async def test_workflow_parts_are_stored_before_the_existing_draft_uses_them(
    client: httpx.AsyncClient, acme: FakeForge, held_setup: Setup
) -> None:
    await sign_in_as(client, acme, 8)
    assert (
        await client.post(
            "/api/v1/workflows", json={"owner": "bob", "name": "parts"}, headers=ORIGIN
        )
    ).status_code == 201
    workflow = "/api/v1/workflows/bob/parts"
    upload = await _sent(client, acme, workflow + "/part-uploads", b"workflow data")
    await held_setup.settle()
    assert (await client.get(f"{workflow}/part-uploads/{upload}")).json()["status"] == "stored"
    draft = (await client.get(workflow)).json()["draft"]
    saved = await client.put(
        workflow + "/draft",
        json={
            "content": draft["content"],
            "token": draft["token"],
            "changes": [{"path": "data.bin", "token": None, "upload": upload}],
        },
        headers=ORIGIN,
    )
    assert saved.status_code == 200, saved.text
    assert acme.objects.uploads == {}


@pytest.mark.parametrize("operation", ["read", "sign", "finish", "abort"])
async def test_another_owner_cannot_operate_a_task_transfer(
    client: httpx.AsyncClient, world: FakeForge, operation: str
) -> None:
    await run_contest(client)
    base = f"{TASK}/organise/part-uploads"
    started = await client.post(
        base, json={"path": "data.bin", "size": 1, "sha256": "f" * 64}, headers=ORIGIN
    )
    assert started.status_code == 201
    upload = started.json()["id"]
    assert isinstance(upload, str)
    await sign_in_as(client, world, 20)
    if operation == "read":
        result = await client.get(f"{base}/{upload}")
    elif operation == "abort":
        result = await client.delete(f"{base}/{upload}", headers=ORIGIN)
    else:
        body = {"numbers": [1]} if operation == "sign" else {"parts": [{"number": 1, "etag": "x"}]}
        result = await client.post(f"{base}/{upload}/{operation}", json=body, headers=ORIGIN)
    assert result.status_code == 404
    assert result.json()["code"] == "not_found"
