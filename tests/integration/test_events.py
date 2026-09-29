"""The door the forge pushes an org's events through admits a body signed
with that org's secret, refuses a wrong signature and an org it has no
secret for alike, refuses a body over 1 MiB before reading past it, and
needs no Origin, since the forge sends none.
"""

import hashlib
import hmac
from collections.abc import AsyncIterator
from urllib.parse import urlsplit

import httpx
import pytest
from forge.api.events import EVENTS_PATH
from forge.testing import FakeForge

BODY = b'{"ref": "refs/heads/main"}'
MIB = 1024 * 1024


@pytest.fixture
def door(acme: FakeForge) -> tuple[str, bytes]:
    """Where the forge was told to push acme's events, and with what secret."""
    push = acme.state.orgs["acme"].event_push
    assert push is not None
    url, secret = push
    return urlsplit(url).path, secret.encode()


def _signed(secret: bytes, body: bytes = BODY) -> str:
    return hmac.new(secret, body, hashlib.sha256).hexdigest()


async def test_a_signed_event_is_let_in_without_an_origin(
    client: httpx.AsyncClient, door: tuple[str, bytes]
) -> None:
    path, secret = door

    admitted = await client.post(
        path, content=BODY, headers={"X-Forgejo-Signature": _signed(secret)}
    )

    assert path == f"{EVENTS_PATH}/acme"
    assert admitted.status_code == 204


async def test_the_older_signature_header_is_read_too(
    client: httpx.AsyncClient, door: tuple[str, bytes]
) -> None:
    path, secret = door

    admitted = await client.post(path, content=BODY, headers={"X-Gitea-Signature": _signed(secret)})

    assert admitted.status_code == 204


@pytest.mark.parametrize(
    "headers",
    [{"X-Forgejo-Signature": "0" * 64}, {}],
    ids=["wrong", "missing"],
)
async def test_an_event_that_is_not_signed_by_the_org_is_refused(
    client: httpx.AsyncClient, door: tuple[str, bytes], headers: dict[str, str]
) -> None:
    path, _ = door

    refused = await client.post(path, content=BODY, headers=headers)

    assert refused.status_code == 403
    assert refused.json()["code"] == "forbidden"


async def test_a_signature_over_another_body_is_refused(
    client: httpx.AsyncClient, door: tuple[str, bytes]
) -> None:
    path, secret = door

    refused = await client.post(
        path, content=BODY + b" ", headers={"X-Forgejo-Signature": _signed(secret)}
    )

    assert refused.status_code == 403


async def test_an_org_with_no_secret_is_refused_like_a_wrong_signature(
    client: httpx.AsyncClient, door: tuple[str, bytes]
) -> None:
    _, secret = door

    refused = await client.post(
        f"{EVENTS_PATH}/nobody",
        content=BODY,
        headers={"X-Forgejo-Signature": _signed(secret)},
    )

    assert refused.status_code == 403
    assert refused.json()["code"] == "forbidden"
    assert refused.json()["detail"] == "The event's signature does not match."


async def test_a_body_of_exactly_one_mib_is_read(
    client: httpx.AsyncClient, door: tuple[str, bytes]
) -> None:
    path, secret = door
    body = b"x" * MIB

    admitted = await client.post(
        path, content=body, headers={"X-Forgejo-Signature": _signed(secret, body)}
    )

    assert admitted.status_code == 204


async def test_a_body_declared_over_one_mib_is_refused(
    client: httpx.AsyncClient, door: tuple[str, bytes]
) -> None:
    path, secret = door
    body = b"x" * (MIB + 1)

    refused = await client.post(
        path, content=body, headers={"X-Forgejo-Signature": _signed(secret, body)}
    )

    assert refused.status_code == 413
    assert refused.json()["code"] == "payload_too_large"


async def test_a_body_with_no_length_is_cut_off_past_one_mib(
    client: httpx.AsyncClient, door: tuple[str, bytes]
) -> None:
    path, secret = door
    sent = 0

    async def chunks() -> AsyncIterator[bytes]:
        nonlocal sent
        for _ in range(4):
            sent += 1
            yield b"x" * (MIB // 2)

    refused = await client.post(
        path, content=chunks(), headers={"X-Forgejo-Signature": _signed(secret)}
    )

    assert refused.status_code == 413
    assert refused.json()["code"] == "payload_too_large"
    assert "content-length" not in {name.lower() for name in refused.request.headers}
    assert sent == 3


async def test_a_length_that_is_not_a_number_is_read_as_no_length(
    client: httpx.AsyncClient, door: tuple[str, bytes]
) -> None:
    path, secret = door

    admitted = await client.post(
        path,
        content=BODY,
        headers={b"X-Forgejo-Signature": _signed(secret).encode(), b"Content-Length": b"\xb2"},
    )

    assert admitted.status_code == 204
