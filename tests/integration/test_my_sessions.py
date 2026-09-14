"""Sessions are per device, and the account page can end them one at a time."""

from collections.abc import AsyncIterator

import httpx
import pytest
from fastapi import FastAPI

from tests.integration import login_flow
from tests.integration.conftest import APP_URL
from unicon.api.cookies import SESSION_COOKIE


@pytest.fixture
async def other_device(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url=APP_URL) as second:
        yield second


async def test_both_devices_are_listed_with_this_one_marked(
    client: httpx.AsyncClient, other_device: httpx.AsyncClient, browser: httpx.AsyncClient
) -> None:
    await login_flow.log_in(client, browser)
    await login_flow.log_in(other_device, browser)

    listed = (await client.get("/api/v1/me/sessions")).json()

    assert len(listed) == 2
    assert [one["current"] for one in listed].count(True) == 1
    assert all(len(one["id"]) == 64 for one in listed)


async def test_one_session_can_be_ended_from_the_other(
    client: httpx.AsyncClient, other_device: httpx.AsyncClient, browser: httpx.AsyncClient
) -> None:
    await login_flow.log_in(client, browser)
    await login_flow.log_in(other_device, browser)
    listed = (await client.get("/api/v1/me/sessions")).json()
    elsewhere = next(one for one in listed if not one["current"])

    ended = await client.request(
        "DELETE", f"/api/v1/me/sessions/{elsewhere['id']}", headers={"Origin": APP_URL}
    )

    assert ended.status_code == 204
    assert len((await client.get("/api/v1/me/sessions")).json()) == 1
    assert (await other_device.get("/api/v1/me")).status_code == 401


async def test_a_session_that_is_not_yours_is_not_found(
    client: httpx.AsyncClient, browser: httpx.AsyncClient
) -> None:
    await login_flow.log_in(client, browser)

    missing = await client.request(
        "DELETE", f"/api/v1/me/sessions/{'ab' * 32}", headers={"Origin": APP_URL}
    )

    assert missing.status_code == 404
    assert missing.json()["code"] == "not_found"


async def test_signing_out_everywhere_includes_this_device(
    client: httpx.AsyncClient, other_device: httpx.AsyncClient, browser: httpx.AsyncClient
) -> None:
    await login_flow.log_in(client, browser)
    await login_flow.log_in(other_device, browser)

    ended = await client.request("DELETE", "/api/v1/me/sessions", headers={"Origin": APP_URL})

    assert ended.status_code == 204
    assert SESSION_COOKIE not in client.cookies
    assert (await client.get("/api/v1/me")).status_code == 401
    assert (await other_device.get("/api/v1/me")).status_code == 401
