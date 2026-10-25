import hashlib

import httpx
from forge.testing import FakeForge

from tests.integration.conftest import ORIGIN, sign_in_as


async def test_an_owner_uploads_saves_replaces_removes_and_versions_files(
    client: httpx.AsyncClient, acme: FakeForge
) -> None:
    await sign_in_as(client, acme, 8)
    made = await client.post(
        "/api/v1/workflows", json={"owner": "bob", "name": "files"}, headers=ORIGIN
    )
    assert made.status_code == 201
    base = "/api/v1/workflows/bob/files"
    draft = (await client.get(base)).json()["draft"]
    content = b"print(42)\n"
    slot = await client.post(
        f"{base}/uploads",
        json={
            "path": "scorer/main.py",
            "size": len(content),
            "sha256": hashlib.sha256(content).hexdigest(),
        },
        headers=ORIGIN,
    )
    assert slot.status_code == 201, slot.text
    upload = slot.json()["id"]
    door = await client.get(
        "/-/uploads/door",
        headers={
            "X-Original-URI": f"/-/uploads/{upload}",
            "X-Upload-Length": str(len(content)),
        },
    )
    assert door.status_code == 204, door.text
    acme.uploads.send(door.headers["X-Forge-Path"], door.headers["X-Forge-Authorization"], content)
    completed = await client.post(f"{base}/uploads/{upload}/complete", headers=ORIGIN)
    assert completed.status_code == 200, completed.text
    assert completed.json()["status"] == "verified"
    repo = acme.state.repos[("bob", "files.workflow")]
    saved = await client.put(
        f"{base}/draft",
        json={
            "content": draft["content"],
            "token": draft["token"],
            "changes": [{"path": "scorer/main.py", "token": None, "upload": upload}],
        },
        headers=ORIGIN,
    )
    assert saved.status_code == 200, saved.text
    revision = saved.json()["revision"]
    tree = await client.get(f"{base}/tree", params={"path": "scorer"})
    assert tree.status_code == 200
    [file] = tree.json()
    assert file["path"] == "scorer/main.py"
    frozen = await client.post(
        f"{base}/versions",
        json={"version": "v1", "token": saved.json()["token"], "revision": revision},
        headers=ORIGIN,
    )
    assert frozen.status_code == 201, frozen.text
    replaced = await client.put(
        f"{base}/draft",
        json={
            "content": saved.json()["content"],
            "token": saved.json()["token"],
            "changes": [{"path": "scorer/main.py", "token": file["token"], "content": "print(43)"}],
        },
        headers=ORIGIN,
    )
    assert replaced.status_code == 200, replaced.text
    current = await client.get(f"{base}/files/scorer/main.py")
    assert current.status_code == 200
    assert current.json()["content"] == "print(43)"
    file = current.json()
    removed = await client.put(
        f"{base}/draft",
        json={
            "content": saved.json()["content"],
            "token": saved.json()["token"],
            "changes": [{"path": "scorer/main.py", "token": file["token"], "remove": True}],
        },
        headers=ORIGIN,
    )
    assert removed.status_code == 200, removed.text
    assert (await client.get(f"{base}/tree", params={"path": "scorer"})).json() == []
    assert (
        hashlib.sha256(content).hexdigest().encode()
        in acme.state.files_at(repo, repo.versions["v1"])["scorer/main.py"]
    )
    assert (
        await client.post(
            f"{base}/versions", json={"version": "v2", "revision": revision}, headers=ORIGIN
        )
    ).status_code == 409
    await sign_in_as(client, acme, 7)
    assert (await client.get(f"{base}/tree")).status_code == 404
    assert (
        await client.post(f"{base}/uploads/{upload}/complete", headers=ORIGIN)
    ).status_code == 404
