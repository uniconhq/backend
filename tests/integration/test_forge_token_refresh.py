"""Keeping the person's Forgejo token usable without two tabs fighting over it.
Any path that needs the token refreshes it first if it is nearly dead, and
concurrent requests produce one new pair, not two.
"""

import asyncio
from datetime import UTC, datetime, timedelta

import httpx

from tests.fakes.forge import FakeForge
from tests.integration import database_probe, login_flow


def _about_to_expire(database_url: str) -> None:
    database_probe.set_column(
        database_url, "forge_token_expires_at", datetime.now(UTC) + timedelta(minutes=1)
    )


async def test_a_token_near_expiry_is_refreshed_once(
    client: httpx.AsyncClient,
    browser: httpx.AsyncClient,
    forge: FakeForge,
    migrated_database_url: str,
) -> None:
    await login_flow.log_in(client, browser)
    before = database_probe.rows(migrated_database_url)[0]
    _about_to_expire(migrated_database_url)

    me = await client.get("/api/v1/me")

    assert me.status_code == 200
    assert forge.refreshes == 1
    after = database_probe.rows(migrated_database_url)[0]
    assert after["forge_refresh_token"] != before["forge_refresh_token"]
    assert after["forge_token_expires_at"] > before["forge_token_expires_at"]


async def test_two_requests_at_once_refresh_once(
    client: httpx.AsyncClient,
    browser: httpx.AsyncClient,
    forge: FakeForge,
    migrated_database_url: str,
) -> None:
    await login_flow.log_in(client, browser)
    _about_to_expire(migrated_database_url)
    forge.refresh_delay = 0.2

    both = await asyncio.gather(client.get("/api/v1/me"), client.get("/api/v1/me"))

    assert [answer.status_code for answer in both] == [200, 200]
    assert forge.refreshes == 1


async def test_a_forge_that_refuses_this_client_does_not_end_the_session(
    client: httpx.AsyncClient,
    browser: httpx.AsyncClient,
    forge: FakeForge,
    migrated_database_url: str,
) -> None:
    await login_flow.log_in(client, browser)
    _about_to_expire(migrated_database_url)
    forge.client_secret = "rotated-in-the-forge"

    me = await client.get("/api/v1/me")

    assert me.status_code == 502
    assert me.json()["code"] == "forge_misconfigured"
    assert database_probe.rows(migrated_database_url)[0]["revoked_at"] is None


async def test_a_refused_refresh_ends_the_session(
    client: httpx.AsyncClient,
    browser: httpx.AsyncClient,
    forge: FakeForge,
    migrated_database_url: str,
) -> None:
    await login_flow.log_in(client, browser)
    _about_to_expire(migrated_database_url)
    forge.refuse_refresh = True

    me = await client.get("/api/v1/me")

    assert me.status_code == 401
    assert me.json()["code"] == "forge_reauth"
    ended = database_probe.rows(migrated_database_url)[0]
    assert ended["revoked_at"] is not None
    assert ended["forge_access_token"] == b""
    assert ended["forge_refresh_token"] == b""
