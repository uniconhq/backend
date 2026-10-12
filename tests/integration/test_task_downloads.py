"""A task's own files through the download door, as the proxy asks for them:
`/-/downloads/<org>/<contest>/<task>/versions/<version>/<path>`, the version
a read of the file named. The door opens, with where at the forge the file
is read whole, the credential to present there and the name the download
takes, for whoever holds a role reaching the task, observer or above, a
typed file and an upload alike. Nobody else, an entrant included, gets a
door, and every address that is not one is refused without saying why.
"""

import hashlib
import re
from urllib.parse import quote

import httpx
import pytest
from forge.api.errors import NotFound
from forge.api.types import Role, Scope
from forge.api.uploads import Door
from forge.testing import FakeForge, Setup

from tests.integration.conftest import CONTEST, ORIGIN, SUM, TASK, read, sign_in_as

DOOR = "/-/downloads/door"
DOWNLOADS = "/-/downloads/acme/spring/sum/versions"
DATA = b"a test's answer, pretend it is gigabytes\n" * 64
UPLOADED = "data/answer.bin"


async def _download(client: httpx.AsyncClient, address: str) -> httpx.Response:
    """What the proxy asks for a download, with the header it sends."""
    return await client.get(DOOR, headers={"X-Original-URI": address})


async def _version(client: httpx.AsyncClient, path: str) -> str:
    """The version a read of the file names, as the page offering the
    download read it.
    """
    file = await read(client, f"{TASK}/files/{path}")
    version: str = file["version"]
    assert re.fullmatch(r"[0-9a-f]{40}", version), version
    return version


async def _write(client: httpx.AsyncClient, path: str, content: str) -> None:
    current = await client.get(f"{TASK}/files/{path}")
    token = current.json()["token"] if current.status_code == 200 else None
    written = await client.put(
        f"{TASK}/files/{path}",
        json={"encoding": "utf-8", "content": content, "token": token},
        headers=ORIGIN,
    )
    assert written.status_code == 200, written.text


async def _upload(client: httpx.AsyncClient, forge: FakeForge) -> None:
    """DATA uploaded into the task at UPLOADED and saved, the way the
    organiser's browser does it.
    """
    slot = await client.post(
        f"{TASK}/organise/uploads",
        json={"path": UPLOADED, "size": len(DATA), "sha256": hashlib.sha256(DATA).hexdigest()},
        headers=ORIGIN,
    )
    assert slot.status_code == 201, slot.text
    door = await client.get(
        "/-/uploads/door",
        headers={
            "X-Original-URI": f"/-/uploads/{slot.json()['id']}",
            "X-Upload-Length": str(len(DATA)),
        },
    )
    forge.uploads.send(door.headers["X-Forge-Path"], door.headers["X-Forge-Authorization"], DATA)
    completed = await client.post(f"{TASK}/uploads/{slot.json()['id']}/complete", headers=ORIGIN)
    assert completed.status_code == 200, completed.text
    saved = await client.post(
        f"{TASK}/save",
        json={"changes": [{"path": UPLOADED, "upload": slot.json()["id"], "token": None}]},
        headers=ORIGIN,
    )
    assert saved.status_code == 200, saved.text


def _door(opened: httpx.Response) -> Door:
    assert opened.status_code == 204, opened.text
    return Door(opened.headers["X-Forge-Path"], opened.headers["X-Forge-Authorization"])


async def test_an_organiser_downloads_a_typed_file_and_an_upload_at_the_version_read(
    client: httpx.AsyncClient, sum_task: FakeForge
) -> None:
    await _upload(client, sum_task)
    typed = await read(client, f"{TASK}/files/task.yaml")
    typed_at = await _version(client, "task.yaml")
    uploaded_at = await _version(client, UPLOADED)

    statement = await _download(client, f"{DOWNLOADS}/{typed_at}/task.yaml")
    upload = await _download(client, f"{DOWNLOADS}/{uploaded_at}/data/answer.bin")

    door = _door(statement)
    assert re.search(rf"/media/task\.yaml\?ref={typed_at}$", door.path), door.path
    assert await sum_task.content.fetch(door) == typed["content"].encode()
    assert statement.headers["X-Download-Disposition"] == 'attachment; filename="task.yaml"'
    # The upload's own bytes, not the pointer its commit holds.
    assert await sum_task.content.fetch(_door(upload)) == DATA
    assert upload.headers["X-Download-Disposition"] == 'attachment; filename="answer.bin"'


async def test_a_download_is_the_file_as_it_was_at_the_version_named(
    client: httpx.AsyncClient, sum_task: FakeForge
) -> None:
    await _write(client, "notes.txt", "first\n")
    first = await _version(client, "notes.txt")
    await _write(client, "notes.txt", "second\n")

    then = await _download(client, f"{DOWNLOADS}/{first}/notes.txt")
    at = await read(client, f"{TASK}/files/notes.txt?at={first}")

    assert at["version"] == first
    assert await sum_task.content.fetch(_door(then)) == b"first\n"


async def test_a_listed_file_downloads_at_the_version_the_listing_names(
    client: httpx.AsyncClient, sum_task: FakeForge
) -> None:
    await _write(client, "data/big.txt", "listed\n")
    listing = await client.get(f"{TASK}/tree", params={"path": "data"})
    await _write(client, "data/big.txt", "saved since\n")

    (entry,) = listing.json()
    then = await _download(client, f"{DOWNLOADS}/{entry['version']}/data/big.txt")

    assert re.fullmatch(r"[0-9a-f]{40}", entry["version"]), entry
    assert await sum_task.content.fetch(_door(then)) == b"listed\n"


async def test_each_segment_of_the_path_is_decoded_on_its_own(
    client: httpx.AsyncClient, sum_task: FakeForge
) -> None:
    name = "my notes é.txt"
    await _write(client, f"data/{name}", "hello\n")
    version = await _version(client, f"data/{name}")

    opened = await _download(client, f"{DOWNLOADS}/{version}/data/{quote(name)}")

    assert await sum_task.content.fetch(_door(opened)) == b"hello\n"
    assert opened.headers["X-Download-Disposition"] == (
        f"attachment; filename*=UTF-8''{quote(name, safe='')}"
    )


@pytest.mark.parametrize(
    "scope",
    [SUM, Scope("acme", "spring"), Scope("acme")],
    ids=["the task", "its contest", "its org"],
)
async def test_an_observer_wherever_it_reaches_the_task_gets_the_door(
    client: httpx.AsyncClient, world: FakeForge, scope: Scope
) -> None:
    version = await _version(client, "task.yaml")
    await world.orgs.grant_role(20, scope, Role.OBSERVER)
    await sign_in_as(client, world, 20)

    opened = await _download(client, f"{DOWNLOADS}/{version}/task.yaml")

    assert opened.status_code == 204, opened.text


async def test_nobody_else_gets_a_door_an_entrant_included(
    client: httpx.AsyncClient, entered: FakeForge, held_setup: Setup
) -> None:
    await sign_in_as(client, entered, 7)
    version = await _version(client, "task.yaml")
    address = f"{DOWNLOADS}/{version}/task.yaml"
    made = await client.post(f"{CONTEST}/tasks", json={"name": "other"}, headers=ORIGIN)
    assert made.status_code == 201, made.text
    entered.add_user(21, "dee")
    await entered.orgs.grant_role(21, Scope("acme", "spring", "other"), Role.ADMIN)

    await sign_in_as(client, entered, 20)
    entrant = await _download(client, address)
    await sign_in_as(client, entered, 21)
    elsewhere = await _download(client, address)
    entered.add_user(22, "eve")
    await sign_in_as(client, entered, 22)
    stranger = await _download(client, address)
    client.cookies.clear()
    nobody = await _download(client, address)

    assert [entrant.status_code, elsewhere.status_code, stranger.status_code] == [403, 403, 403]
    assert nobody.status_code == 401
    for refused in (entrant, elsewhere, stranger, nobody):
        assert "X-Forge-Authorization" not in refused.headers
        assert "observer" not in refused.text
    assert entered.calls_to("media_door") == []


@pytest.mark.parametrize(
    "address",
    [
        "{at}/../task.yaml",
        "{at}/%2E%2E/task.yaml",
        "{at}/data//task.yaml",
        "{at}/task.yaml/",
        "{at}",
        "{at}/",
        "{at}/%FF.txt",
        "{at}/a%3Fb",
        "main/task.yaml",
        "HEAD/task.yaml",
        "0123abc/task.yaml",
        "{upper}/task.yaml",
        "/task.yaml",
        "{at}/data%2Fanswer.bin",
    ],
    ids=[
        "up",
        "up encoded",
        "an empty part",
        "a trailing slash",
        "no path",
        "an empty path",
        "not utf-8",
        "a query in a name",
        "a branch",
        "head",
        "short",
        "upper case",
        "no version",
        "an encoded slash",
    ],
)
async def test_the_door_refuses_anything_else_without_saying_why(
    client: httpx.AsyncClient, sum_task: FakeForge, address: str
) -> None:
    version = await _version(client, "task.yaml")

    refused = await _download(
        client, f"{DOWNLOADS}/{address.format(at=version, upper=version.upper())}"
    )

    assert refused.status_code == 403
    assert "X-Forge-Authorization" not in refused.headers
    assert sum_task.calls_to("media_door") == []


async def test_a_file_or_a_version_the_task_lacks_is_the_forges_to_refuse(
    client: httpx.AsyncClient, sum_task: FakeForge
) -> None:
    # Nothing is read to open the door, so the forge refuses as it serves,
    # and the proxy turns that into its own 404.
    version = await _version(client, "task.yaml")

    missing = await _download(client, f"{DOWNLOADS}/{version}/nothing.txt")
    elsewhere = await _download(client, f"{DOWNLOADS}/{'f' * 40}/task.yaml")

    for opened in (missing, elsewhere):
        with pytest.raises(NotFound):
            await sum_task.content.fetch(_door(opened))


@pytest.mark.parametrize(
    "address",
    [
        "/-/downloads/acme/spring/nothing/versions/{at}/task.yaml",
        "/-/downloads/acme/autumn/sum/versions/{at}/task.yaml",
        "/-/downloads/acme/spring/sum/version/{at}/task.yaml",
        "/-/downloads/acme/spring%2Fsum/sum/versions/{at}/task.yaml",
    ],
    ids=["a task not there", "a contest not there", "not the word", "an encoded slash"],
)
async def test_the_door_refuses_a_place_that_is_not_there(
    client: httpx.AsyncClient, sum_task: FakeForge, address: str
) -> None:
    version = await _version(client, "task.yaml")

    refused = await _download(client, address.format(at=version))

    assert refused.status_code == 403
    assert "X-Forge-Authorization" not in refused.headers
