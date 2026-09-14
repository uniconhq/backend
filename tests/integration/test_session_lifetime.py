"""A session that has ended says so, and takes its cookie with it. Revoked, past
its hard expiry, or idle too long: all three answer 401 `session_expired` and
clear the cookie.
"""

from datetime import UTC, datetime, timedelta

import httpx

from tests.integration import database_probe, login_flow
from tests.integration.conftest import APP_URL
from unicon.api.cookies import SESSION_COOKIE

HEADERS = {"Origin": APP_URL}


def _cookie_is_cleared(response: httpx.Response) -> bool:
    header = response.headers.get("set-cookie", "")
    return SESSION_COOKIE in header and "Max-Age=0" in header


async def test_a_session_past_its_hard_expiry_is_over(
    client: httpx.AsyncClient, browser: httpx.AsyncClient, migrated_database_url: str
) -> None:
    await login_flow.log_in(client, browser)
    database_probe.set_column(
        migrated_database_url, "expires_at", datetime.now(UTC) - timedelta(seconds=1)
    )

    me = await client.get("/api/v1/me")

    assert me.status_code == 401
    assert me.json()["code"] == "session_expired"
    assert _cookie_is_cleared(me)


async def test_a_session_nobody_used_is_over(
    client: httpx.AsyncClient, browser: httpx.AsyncClient, migrated_database_url: str
) -> None:
    await login_flow.log_in(client, browser)
    database_probe.set_column(
        migrated_database_url, "last_seen_at", datetime.now(UTC) - timedelta(days=15)
    )

    me = await client.get("/api/v1/me")

    assert me.status_code == 401
    assert me.json()["code"] == "session_expired"
    assert _cookie_is_cleared(me)


async def test_a_revoked_session_is_over(
    client: httpx.AsyncClient, browser: httpx.AsyncClient, migrated_database_url: str
) -> None:
    await login_flow.log_in(client, browser)
    database_probe.set_column(migrated_database_url, "revoked_at", datetime.now(UTC))

    me = await client.get("/api/v1/me")

    assert me.status_code == 401
    assert me.json()["code"] == "session_expired"
    assert _cookie_is_cleared(me)


async def test_ending_the_session_you_are_in_signs_you_out_here(
    client: httpx.AsyncClient, browser: httpx.AsyncClient
) -> None:
    await login_flow.log_in(client, browser)
    here = next(one for one in (await client.get("/api/v1/me/sessions")).json() if one["current"])

    ended = await client.request("DELETE", f"/api/v1/me/sessions/{here['id']}", headers=HEADERS)

    assert ended.status_code == 204
    assert _cookie_is_cleared(ended)
    assert SESSION_COOKIE not in client.cookies


async def test_a_session_that_ends_keeps_no_usable_token(
    client: httpx.AsyncClient, browser: httpx.AsyncClient, migrated_database_url: str
) -> None:
    await login_flow.log_in(client, browser)

    await client.post("/api/v1/auth/logout", headers=HEADERS)

    ended = database_probe.rows(migrated_database_url)[0]
    assert ended["revoked_at"] is not None
    assert ended["forge_access_token"] == b""
    assert ended["forge_refresh_token"] == b""


async def test_signing_out_everywhere_disarms_every_row(
    client: httpx.AsyncClient, browser: httpx.AsyncClient, migrated_database_url: str
) -> None:
    await login_flow.log_in(client, browser)

    await client.request("DELETE", "/api/v1/me/sessions", headers=HEADERS)

    assert all(
        row["forge_access_token"] == b"" and row["forge_refresh_token"] == b""
        for row in database_probe.rows(migrated_database_url)
    )
