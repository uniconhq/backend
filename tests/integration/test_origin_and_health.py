"""A state-changing request from another origin is refused, the same request
from the app succeeds, the probes answer on a running stack, and the clock is
forge's.
"""

from datetime import datetime

import httpx
import pytest
from forge.api.errors import NotReady
from forge.testing import FakeClock, FakeForge

from tests.integration.conftest import ORIGIN, sign_in
from unicon.api.cookies import SESSION_COOKIE


async def test_a_request_from_another_origin_is_refused(
    client: httpx.AsyncClient, forge: FakeForge
) -> None:
    await sign_in(client, forge)

    refused = await client.post("/api/v1/auth/logout", headers={"Origin": "https://evil.test"})

    assert refused.status_code == 403
    assert refused.json()["code"] == "origin_mismatch"
    assert (await client.get("/api/v1/me")).status_code == 200


async def test_the_referer_origin_counts_when_origin_is_absent(
    client: httpx.AsyncClient, forge: FakeForge
) -> None:
    await sign_in(client, forge)

    accepted = await client.post(
        "/api/v1/auth/logout", headers={"Referer": "http://app.test/account"}
    )

    assert accepted.status_code == 204


async def test_a_read_is_not_checked(client: httpx.AsyncClient, forge: FakeForge) -> None:
    await sign_in(client, forge)

    assert (
        await client.get("/api/v1/me", headers={"Origin": "https://evil.test"})
    ).status_code == 200


async def test_the_same_request_from_the_app_succeeds(
    client: httpx.AsyncClient, forge: FakeForge
) -> None:
    await sign_in(client, forge)

    assert (await client.post("/api/v1/auth/logout", headers=ORIGIN)).status_code == 204


async def test_the_probes_answer(client: httpx.AsyncClient) -> None:
    assert (await client.get("/healthz")).json() == {"status": "ok"}
    assert (await client.get("/readyz")).json() == {"status": "ready"}
    assert (await client.get("/api/v1/time")).status_code == 200


async def test_a_database_that_does_not_answer_is_not_ready_without_saying_why(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def not_ready() -> None:
        raise NotReady("The database did not answer.")

    monkeypatch.setattr("forge.api.ready", not_ready)

    answer = await client.get("/readyz")

    assert answer.status_code == 503
    assert answer.json() == {"status": "not_ready"}


async def test_the_server_time_is_forges_clock(client: httpx.AsyncClient, clock: FakeClock) -> None:
    answer = await client.get("/api/v1/time")

    assert datetime.fromisoformat(answer.json()["now"]) == clock.now()


async def test_a_request_with_neither_origin_nor_referer_is_refused(
    client: httpx.AsyncClient, forge: FakeForge
) -> None:
    await sign_in(client, forge)

    refused = await client.post("/api/v1/auth/logout")

    assert refused.status_code == 403
    assert refused.json()["code"] == "origin_mismatch"


async def test_a_malformed_earlier_cookie_does_not_hide_the_session(
    client: httpx.AsyncClient, forge: FakeForge
) -> None:
    """A cookie the standard parser gives up on, placed before the session
    cookie, must not turn the check off for the request.
    """
    await sign_in(client, forge)
    session = client.cookies[SESSION_COOKIE]
    client.cookies.clear()

    refused = await client.post(
        "/api/v1/auth/logout",
        headers={"Origin": "https://evil.test", "Cookie": f'x="a b; {SESSION_COOKIE}={session}'},
    )

    assert refused.status_code == 403
    assert refused.json()["code"] == "origin_mismatch"


async def test_a_request_without_a_session_is_checked_too(client: httpx.AsyncClient) -> None:
    refused = await client.post("/api/v1/auth/logout", headers={"Origin": "https://evil.test"})

    assert refused.status_code == 403
    assert refused.json()["code"] == "origin_mismatch"


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/events/forge",
        "/api/v1/events/forge/",
        "/api/v1/events/forge/acme/more",
        "/api/v1/events/forgery/acme",
        "/api/v1/orgs",
        "/api/v1/orgs/acme/roles",
    ],
)
async def test_only_the_forge_event_door_is_let_past_the_check(
    client: httpx.AsyncClient, path: str
) -> None:
    refused = await client.post(path, content=b"{}")

    assert refused.status_code == 403
    assert refused.json()["code"] == "origin_mismatch"
