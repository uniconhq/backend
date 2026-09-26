"""Logging in, and every way it can fail. Each failure lands on the login page
with a code the page renders inline, and none leaves a session row behind.
"""

import logging
import time
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from itsdangerous.timed import TimestampSigner

from tests.fakes.forge import FakeForge
from tests.integration import database_probe, login_flow
from tests.integration.conftest import APP_URL
from tests.integration.running_app import running_app
from unicon.api.cookies import LOGIN_COOKIE, SESSION_COOKIE
from unicon.log import JsonFormatter
from unicon.settings import Settings

AN_HOUR = 3600


def _query_of(response: httpx.Response) -> dict[str, list[str]]:
    return parse_qs(urlsplit(response.headers["location"]).query)


def _error_of(response: httpx.Response) -> str:
    return _query_of(response)["error"][0]


def _live(database_url: str) -> int:
    return len([row for row in database_probe.rows(database_url) if row["revoked_at"] is None])


async def test_a_login_round_trip(
    client: httpx.AsyncClient, browser: httpx.AsyncClient, migrated_database_url: str
) -> None:
    started = await login_flow.start(client, "/contests/1")

    assert started.status_code == 302
    assert started.headers["location"].startswith("http://forge.test/login/oauth/authorize?")
    assert LOGIN_COOKIE in client.cookies

    landed = await client.get((await login_flow.consent(browser, started)).headers["location"])

    assert landed.status_code == 302
    assert landed.headers["location"] == "/contests/1"
    assert SESSION_COOKIE in client.cookies
    assert database_probe.count(migrated_database_url) == 1

    me = await client.get("/api/v1/me")

    assert me.status_code == 200
    assert me.json() == {
        "user_id": 7,
        "username": "ada",
        "name": "Ada Lovelace",
        "email": "ada@example.test",
        "avatar_url": None,
        "degraded": False,
    }


async def test_logging_out_ends_the_session(
    client: httpx.AsyncClient, browser: httpx.AsyncClient
) -> None:
    await login_flow.log_in(client, browser)

    signed_out = await client.post("/api/v1/auth/logout", headers={"Origin": APP_URL})

    assert signed_out.status_code == 204
    assert SESSION_COOKIE not in client.cookies
    assert (await client.get("/api/v1/me")).status_code == 401


async def test_the_stored_token_is_not_the_token(
    client: httpx.AsyncClient,
    browser: httpx.AsyncClient,
    forge: FakeForge,
    migrated_database_url: str,
) -> None:
    await login_flow.log_in(client, browser)

    stored = database_probe.rows(migrated_database_url)[0]

    plaintext = set(forge.access_tokens) | set(forge.refresh_tokens)
    assert all(token.encode() not in stored["forge_access_token"] for token in plaintext)
    assert all(token.encode() not in stored["forge_refresh_token"] for token in plaintext)


async def test_a_state_that_does_not_match_is_refused(
    client: httpx.AsyncClient, browser: httpx.AsyncClient, migrated_database_url: str
) -> None:
    approved = await login_flow.consent(browser, await login_flow.start(client))
    tampered = approved.headers["location"].replace("state=", "state=x")

    landed = await client.get(tampered)

    assert _error_of(landed) == "login_state_invalid"
    assert database_probe.count(migrated_database_url) == 0


async def test_a_login_cookie_older_than_the_window_is_refused(
    client: httpx.AsyncClient,
    browser: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    migrated_database_url: str,
) -> None:
    monkeypatch.setattr(TimestampSigner, "get_timestamp", lambda _: int(time.time()) - AN_HOUR)
    started = await login_flow.start(client)
    monkeypatch.undo()

    landed = await client.get((await login_flow.consent(browser, started)).headers["location"])

    assert _error_of(landed) == "login_state_invalid"
    assert database_probe.count(migrated_database_url) == 0


async def test_a_state_that_is_not_ascii_is_refused(
    client: httpx.AsyncClient, browser: httpx.AsyncClient, migrated_database_url: str
) -> None:
    await login_flow.consent(browser, await login_flow.start(client))

    landed = await client.get("/api/v1/auth/callback", params={"code": "x", "state": "é"})

    assert _error_of(landed) == "login_state_invalid"
    assert database_probe.count(migrated_database_url) == 0


async def test_a_token_the_forge_no_longer_accepts_ends_the_session(
    client: httpx.AsyncClient,
    browser: httpx.AsyncClient,
    forge: FakeForge,
    migrated_database_url: str,
) -> None:
    await login_flow.log_in(client, browser)
    forge.access_tokens.clear()

    me = await client.get("/api/v1/me")

    assert me.status_code == 401
    assert me.json()["code"] == "forge_reauth"
    assert database_probe.rows(migrated_database_url)[0]["revoked_at"] is not None


async def test_a_callback_without_a_login_cookie_is_refused(
    client: httpx.AsyncClient, browser: httpx.AsyncClient, migrated_database_url: str
) -> None:
    approved = await login_flow.consent(browser, await login_flow.start(client))
    client.cookies.delete(LOGIN_COOKIE)

    landed = await client.get(approved.headers["location"])

    assert _error_of(landed) == "login_state_invalid"
    assert database_probe.count(migrated_database_url) == 0


async def test_a_refused_consent_lands_on_the_login_page(client: httpx.AsyncClient) -> None:
    landed = await client.get("/api/v1/auth/callback", params={"error": "access_denied"})

    assert _error_of(landed) == "login_denied"


async def test_a_forge_that_is_down_at_the_exchange_is_reported(
    client: httpx.AsyncClient,
    browser: httpx.AsyncClient,
    forge: FakeForge,
    migrated_database_url: str,
) -> None:
    approved = await login_flow.consent(browser, await login_flow.start(client))
    forge.unreachable = True

    landed = await client.get(approved.headers["location"])

    assert _error_of(landed) == "forge_unreachable"
    assert database_probe.count(migrated_database_url) == 0


async def test_me_degrades_when_the_forge_is_down(
    client: httpx.AsyncClient, browser: httpx.AsyncClient, forge: FakeForge
) -> None:
    await login_flow.log_in(client, browser)
    forge.unreachable = True

    me = await client.get("/api/v1/me")

    assert me.status_code == 200
    assert me.json() == {
        "user_id": 7,
        "username": "ada",
        "name": None,
        "email": None,
        "avatar_url": None,
        "degraded": True,
    }


async def test_the_register_url_follows_the_setting(client: httpx.AsyncClient) -> None:
    open_instance = await client.get("/api/v1/auth/register-url")

    assert open_instance.json() == {"url": "http://forge.test/user/sign_up"}


async def test_signing_in_again_leaves_one_live_session(
    client: httpx.AsyncClient, browser: httpx.AsyncClient, migrated_database_url: str
) -> None:
    await login_flow.log_in(client, browser)
    await login_flow.log_in(client, browser)

    assert database_probe.count(migrated_database_url) == 2
    assert _live(migrated_database_url) == 1
    assert (await client.get("/api/v1/me")).status_code == 200
    assert len((await client.get("/api/v1/me/sessions")).json()) == 1


async def test_the_replayed_callback_starts_no_second_session(
    client: httpx.AsyncClient, browser: httpx.AsyncClient, migrated_database_url: str
) -> None:
    started = await login_flow.start(client)
    login_cookie = client.cookies[LOGIN_COOKIE]
    landing = (await login_flow.consent(browser, started)).headers["location"]
    await client.get(landing)
    client.cookies.set(LOGIN_COOKIE, login_cookie, domain="app.test", path="/")

    replayed = await client.get(landing)

    assert _error_of(replayed) == "login_state_invalid"
    assert database_probe.count(migrated_database_url) == 1
    assert _live(migrated_database_url) == 1
    assert (await client.get("/api/v1/me")).status_code == 200


async def test_a_failed_login_keeps_where_the_person_was_going(
    client: httpx.AsyncClient, browser: httpx.AsyncClient
) -> None:
    approved = await login_flow.consent(browser, await login_flow.start(client, "/contests/4"))
    tampered = approved.headers["location"].replace("state=", "state=x")

    landed = await client.get(tampered)

    assert _query_of(landed)["next"] == ["/contests/4"]


async def test_a_forge_that_refuses_this_client_is_not_an_expired_login(
    client: httpx.AsyncClient, browser: httpx.AsyncClient, forge: FakeForge
) -> None:
    approved = await login_flow.consent(browser, await login_flow.start(client))
    forge.client_secret = "rotated-in-the-forge"

    landed = await client.get(approved.headers["location"])

    assert _error_of(landed) == "forge_misconfigured"


async def test_a_refusal_is_logged_with_its_code_and_no_secret(
    client: httpx.AsyncClient,
    browser: httpx.AsyncClient,
    caplog: pytest.LogCaptureFixture,
) -> None:
    approved = await login_flow.consent(browser, await login_flow.start(client))
    landing = approved.headers["location"]
    arrived = parse_qs(urlsplit(landing).query)
    state, code = arrived["state"][0], arrived["code"][0]
    client.cookies.delete(LOGIN_COOKIE)

    with caplog.at_level(logging.INFO, logger="unicon.services.login"):
        await client.get(landing)

    written = "\n".join(JsonFormatter().format(record) for record in caplog.records)
    assert "login_state_invalid" in written
    assert state not in written
    assert state[:8] in written
    assert code not in written


async def test_the_register_url_is_nothing_when_sign_ups_are_closed(settings: Settings) -> None:
    closed = settings.model_copy(update={"forge_registration_open": False})

    async with running_app(closed) as app:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url=APP_URL) as visitor:
            answer = await visitor.get("/api/v1/auth/register-url")

    assert answer.json() == {"url": None}
