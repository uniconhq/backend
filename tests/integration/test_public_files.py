"""A task's public files over HTTP, the files under its `public/` a statement
shows, such as its images. Each is answered as its bytes, typed by its
ending, never sniffed, kept a minute by the reader's browser alone, and an
SVG under a policy that runs no script. A visitor reads them where the
statement is public, a signed-in person where they read the task's page,
and an organiser of the task before it is released; anyone else, a path
outside `public/` and a file that is not there are all not found, and a
file larger than a page is served is refused with its limit.
"""

import base64
from typing import Any

import httpx
import pytest
from forge.testing import FakeForge

from tests.integration.conftest import ORIGIN, TASK, run_contest, sign_in_as
from unicon.api.cookies import SESSION_COOKIE

PNG = b"\x89PNG\r\n\x1a\n not really a picture"
SVG = '<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>\n'
PUBLIC = f"{TASK}/public"
MOST = 10 * 1024 * 1024


def _typed(path: str, content: str) -> dict[str, Any]:
    return {"path": path, "encoding": "utf-8", "content": content, "token": None}


def _binary(path: str, content: bytes) -> dict[str, Any]:
    encoded = base64.b64encode(content).decode()
    return {"path": path, "encoding": "base64", "content": encoded, "token": None}


async def _publish_public(client: httpx.AsyncClient) -> None:
    """acme/spring/sum published with its public files, saved by ada."""
    saved = await client.post(
        f"{TASK}/save",
        json={
            "changes": [
                _binary("public/figure.png", PNG),
                _binary("public/Photo.JPG", PNG),
                _typed("public/diagram.svg", SVG),
                _typed("public/data/train.csv", "a,b\n1,2\n"),
            ]
        },
        headers=ORIGIN,
    )
    assert saved.status_code == 200 and "number" in saved.json(), saved.text


@pytest.fixture
async def public(client: httpx.AsyncClient, world: FakeForge) -> FakeForge:
    """acme/spring running for everyone, with sum published with its public
    files, read by a visitor with no session.
    """
    await run_contest(client, visibility="everyone")
    await _publish_public(client)
    client.cookies.clear()
    return world


async def test_a_visitor_reads_a_picture_as_its_bytes_typed_by_its_ending(
    client: httpx.AsyncClient, public: FakeForge
) -> None:
    found = await client.get(f"{PUBLIC}/figure.png")

    assert found.status_code == 200, found.text
    assert found.content == PNG
    assert found.headers["content-type"] == "image/png"
    assert found.headers["x-content-type-options"] == "nosniff"
    assert found.headers["cache-control"] == "private, max-age=60"
    assert "content-security-policy" not in found.headers


@pytest.mark.parametrize(
    ("path", "kind"),
    [
        ("Photo.JPG", "image/jpeg"),
        ("data/train.csv", "application/octet-stream"),
        ("diagram.svg", "image/svg+xml"),
    ],
)
async def test_each_file_is_typed_by_its_ending_and_anything_else_is_bytes(
    client: httpx.AsyncClient, public: FakeForge, path: str, kind: str
) -> None:
    found = await client.get(f"{PUBLIC}/{path}")

    assert found.status_code == 200, found.text
    assert found.headers["content-type"] == kind
    assert found.headers["x-content-type-options"] == "nosniff"


async def test_an_svg_opened_on_its_own_runs_no_script(
    client: httpx.AsyncClient, public: FakeForge
) -> None:
    found = await client.get(f"{PUBLIC}/diagram.svg")

    assert found.text == SVG
    assert found.headers["content-security-policy"] == (
        "default-src 'none'; style-src 'unsafe-inline'; sandbox"
    )


@pytest.mark.parametrize(
    "path",
    ["missing.png", "data", "%2E%2E/task.yaml", "%2E%2E/tests/main/1/input", "a//b.png", ""],
)
async def test_a_path_outside_public_or_not_there_is_not_found_and_says_nothing_more(
    client: httpx.AsyncClient, public: FakeForge, path: str
) -> None:
    found = await client.get(f"{PUBLIC}/{path}")

    assert found.status_code == 404
    body = found.json()
    assert body["code"] == "not_found"
    assert body["detail"] in ("There is no such file.", "Not Found")
    assert "acme" not in found.text and "forge" not in found.text.lower()


async def test_a_contest_for_the_signed_in_shows_its_files_to_them_and_not_to_a_visitor(
    client: httpx.AsyncClient, world: FakeForge
) -> None:
    await run_contest(client, visibility="signed-in")
    await _publish_public(client)
    client.cookies.clear()

    visitor = await client.get(f"{PUBLIC}/figure.png")
    await sign_in_as(client, world, 20)
    stranger = await client.get(f"{PUBLIC}/figure.png")

    assert (visitor.status_code, visitor.json()["detail"]) == (404, "There is no such task.")
    assert (stranger.status_code, stranger.content) == (200, PNG)


async def test_a_hidden_contests_files_are_its_organisers_and_not_a_strangers(
    client: httpx.AsyncClient, world: FakeForge
) -> None:
    await run_contest(client, visibility="hidden")
    await _publish_public(client)

    organiser = await client.get(f"{PUBLIC}/figure.png")
    await sign_in_as(client, world, 20)
    stranger = await client.get(f"{PUBLIC}/figure.png")

    assert (organiser.status_code, organiser.content) == (200, PNG)
    assert stranger.status_code == 404


async def test_an_organiser_reads_the_files_of_a_task_not_yet_released(
    client: httpx.AsyncClient, world: FakeForge
) -> None:
    await _publish_public(client)

    organiser = await client.get(f"{PUBLIC}/figure.png")
    await sign_in_as(client, world, 20)
    stranger = await client.get(f"{PUBLIC}/figure.png")
    client.cookies.clear()
    visitor = await client.get(f"{PUBLIC}/figure.png")

    assert (organiser.status_code, organiser.content) == (200, PNG)
    assert (stranger.status_code, visitor.status_code) == (404, 404)


async def test_a_cookie_whose_session_is_gone_reads_as_a_visitor(
    client: httpx.AsyncClient, public: FakeForge
) -> None:
    client.cookies.set(SESSION_COOKIE, "not-a-session")

    found = await client.get(f"{PUBLIC}/figure.png")

    assert (found.status_code, found.content) == (200, PNG)


async def test_a_file_larger_than_a_page_is_served_is_refused_with_its_limit(
    client: httpx.AsyncClient, world: FakeForge
) -> None:
    await run_contest(client, visibility="everyone")
    repo = world.state.repos[("acme", "spring.sum.task")]
    world.state.commit(repo, {"public/big.bin": b"x" * (MOST + 1)}, "Big", 7)
    await _publish_public(client)

    refused = await client.get(f"{PUBLIC}/big.bin")

    assert refused.status_code == 409
    body = refused.json()
    assert (body["code"], body["limit"]) == ("public_file_too_large", MOST)
    assert "big.bin" not in body["detail"] and "acme" not in refused.text


async def test_a_task_that_is_not_there_is_not_found(
    client: httpx.AsyncClient, public: FakeForge
) -> None:
    found = await client.get("/api/v1/orgs/acme/contests/spring/tasks/nothing/public/figure.png")

    assert found.status_code == 404
