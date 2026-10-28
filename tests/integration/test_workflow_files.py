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
    classic = acme.state.repos[("unicon", "classic.workflow")].files
    acme.state.commit(
        acme.state.repos[("bob", "files.workflow")],
        {path: data for path, data in classic.items() if path != "workflow.yaml"},
        "Write workflow files",
        8,
    )
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
            "content": classic["workflow.yaml"].decode(),
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


async def test_whoever_reads_a_version_lists_and_downloads_the_files_it_was_frozen_with(
    client: httpx.AsyncClient, acme: FakeForge
) -> None:
    from forge.api.uploads import Door

    await sign_in_as(client, acme, 8)
    made = await client.post(
        "/api/v1/workflows", json={"owner": "bob", "name": "shipped"}, headers=ORIGIN
    )
    assert made.status_code == 201
    base = "/api/v1/workflows/bob/shipped"
    draft = (await client.get(base)).json()["draft"]
    classic = acme.state.repos[("unicon", "classic.workflow")].files
    acme.state.commit(
        acme.state.repos[("bob", "shipped.workflow")],
        {path: data for path, data in classic.items() if path != "workflow.yaml"},
        "Write workflow files",
        8,
    )
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
    upload = slot.json()["id"]
    door = await client.get(
        "/-/uploads/door",
        headers={
            "X-Original-URI": f"/-/uploads/{upload}",
            "X-Upload-Length": str(len(content)),
        },
    )
    acme.uploads.send(door.headers["X-Forge-Path"], door.headers["X-Forge-Authorization"], content)
    await client.post(f"{base}/uploads/{upload}/complete", headers=ORIGIN)
    saved = await client.put(
        f"{base}/draft",
        json={
            "content": classic["workflow.yaml"].decode(),
            "token": draft["token"],
            "changes": [
                {"path": "scorer/main.py", "token": None, "upload": upload},
                {"path": "notes/read me.txt", "token": None, "content": "hello"},
            ],
        },
        headers=ORIGIN,
    )
    assert saved.status_code == 200, saved.text
    frozen = await client.post(
        f"{base}/versions",
        json={
            "version": "v1",
            "token": saved.json()["token"],
            "revision": saved.json()["revision"],
        },
        headers=ORIGIN,
    )
    assert frozen.status_code == 201, frozen.text
    later = await client.put(
        f"{base}/draft",
        json={
            "content": saved.json()["content"],
            "token": saved.json()["token"],
            "changes": [{"path": "notes/later.txt", "token": None, "content": "draft only"}],
        },
        headers=ORIGIN,
    )
    assert later.status_code == 200, later.text

    async def door_to(path: str) -> httpx.Response:
        return await client.get(
            "/-/downloads/door",
            headers={"X-Original-URI": f"/-/downloads/workflows/bob/shipped/versions/{path}"},
        )

    # What v1 was frozen with, not what the draft holds since.
    notes = await client.get(f"{base}/versions/v1/tree", params={"path": "notes"})
    assert notes.status_code == 200, notes.text
    assert [entry["path"] for entry in notes.json()] == ["notes/read me.txt"]
    [scorer] = (await client.get(f"{base}/versions/v1/tree", params={"path": "scorer"})).json()
    assert scorer["upload"]["size"] == len(content)
    opened = await door_to("v1/scorer/main.py")
    assert opened.status_code == 204, opened.text
    assert opened.headers["X-Download-Disposition"] == 'attachment; filename="main.py"'
    given = Door(opened.headers["X-Forge-Path"], opened.headers["X-Forge-Authorization"])
    assert await acme.workflows.fetch(given) == content
    spaced = await door_to("v1/notes/read%20me.txt")
    assert spaced.status_code == 204
    assert (
        await acme.workflows.fetch(
            Door(spaced.headers["X-Forge-Path"], spaced.headers["X-Forge-Authorization"])
        )
        == b"hello"
    )

    # Nothing but a version's own file, named as one.
    for refused in (
        "v2/scorer/main.py",
        "latest/scorer/main.py",
        "v1/notes%2Flater.txt",
        "v1/..%2F..%2Fsecret",
        "v01/scorer/main.py",
    ):
        assert (await door_to(refused)).status_code == 403, refused

    await sign_in_as(client, acme, 7)
    assert (await client.get(f"{base}/versions/v1/tree")).status_code == 404
    assert (await door_to("v1/scorer/main.py")).status_code == 403
    await sign_in_as(client, acme, 8)
    shared = await client.put(f"{base}/visibility", json={"visibility": "public"}, headers=ORIGIN)
    assert shared.status_code == 204, shared.text
    await sign_in_as(client, acme, 7)
    assert [
        entry["path"]
        for entry in (await client.get(f"{base}/versions/v1/tree", params={"path": "notes"})).json()
    ] == ["notes/read me.txt"]
    assert (await door_to("v1/scorer/main.py")).status_code == 204


async def test_whoever_may_change_a_workflow_downloads_its_drafts_files(
    client: httpx.AsyncClient, acme: FakeForge
) -> None:
    from forge.api.uploads import Door

    await sign_in_as(client, acme, 8)
    made = await client.post(
        "/api/v1/workflows", json={"owner": "bob", "name": "drafted"}, headers=ORIGIN
    )
    assert made.status_code == 201
    base = "/api/v1/workflows/bob/drafted"
    draft = (await client.get(base)).json()["draft"]
    saved = await client.put(
        f"{base}/draft",
        json={
            "content": draft["content"],
            "token": draft["token"],
            "changes": [{"path": "notes/read me.txt", "token": None, "content": "hello"}],
        },
        headers=ORIGIN,
    )
    assert saved.status_code == 200, saved.text

    async def door_to(path: str) -> httpx.Response:
        return await client.get(
            "/-/downloads/door",
            headers={"X-Original-URI": f"/-/downloads/workflows/bob/drafted/draft/{path}"},
        )

    opened = await door_to("notes/read%20me.txt")
    assert opened.status_code == 204, opened.text
    assert opened.headers["X-Download-Disposition"] == "attachment; filename*=UTF-8''read%20me.txt"
    given = Door(opened.headers["X-Forge-Path"], opened.headers["X-Forge-Authorization"])
    assert await acme.workflows.fetch(given) == b"hello"
    for refused in ("notes%2Fread%20me.txt", "..%2F..%2Fsecret", ""):
        assert (await door_to(refused)).status_code == 403, refused

    # Its draft is its writers', though a public workflow is read by anyone,
    # and the refusal names no role.
    shared = await client.put(f"{base}/visibility", json={"visibility": "public"}, headers=ORIGIN)
    assert shared.status_code == 204, shared.text
    await sign_in_as(client, acme, 7)
    stranger = await door_to("notes/read%20me.txt")
    assert stranger.status_code == 403
    assert "role" not in stranger.text
