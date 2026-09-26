"""A sign-in through the forge lands the browser back on `next` with a session
cookie set, and every way it can fail lands on the sign-in page with a code.
"""

import httpx
from forge.forges.fake import FakeForge

from tests.integration.conftest import ORIGIN, query_of, sign_in
from unicon.api.cookies import SESSION_COOKIE, SIGN_IN_COOKIE


async def test_a_sign_in_round_trip(client: httpx.AsyncClient, forge: FakeForge) -> None:
    started = await client.get("/api/v1/auth/login", params={"next": "/contests/1"})

    assert started.status_code == 302
    assert started.headers["location"].startswith("http://forge.test/login/oauth/authorize?")
    assert SIGN_IN_COOKIE in client.cookies

    landed = await client.get(forge.consent_redirect(started.headers["location"]))

    assert landed.status_code == 302
    assert landed.headers["location"] == "/contests/1"
    assert SESSION_COOKIE in client.cookies
    assert SIGN_IN_COOKIE not in client.cookies

    me = await client.get("/api/v1/me")

    assert me.status_code == 200
    assert me.json() == {
        "user_id": 7,
        "username": "ada",
        "name": "Ada Lovelace",
        "email": "ada@example.test",
        "avatar_url": None,
        "roles": [],
        "degraded": False,
    }


async def test_a_callback_without_the_sign_in_cookie_is_refused(
    client: httpx.AsyncClient, forge: FakeForge
) -> None:
    started = await client.get("/api/v1/auth/login")
    answer = forge.consent_redirect(started.headers["location"])
    client.cookies.clear()

    landed = await client.get(answer)

    assert landed.status_code == 302
    assert query_of(landed)["error"] == ["sign_in_invalid"]
    assert SESSION_COOKIE not in client.cookies


async def test_a_state_that_does_not_match_is_refused(
    client: httpx.AsyncClient, forge: FakeForge
) -> None:
    started = await client.get("/api/v1/auth/login", params={"next": "/x"})
    answer = forge.consent_redirect(started.headers["location"])

    landed = await client.get(answer.replace("state=", "state=not-"))

    assert query_of(landed) == {"error": ["sign_in_invalid"], "next": ["/x"]}
    assert SESSION_COOKIE not in client.cookies


async def test_a_user_who_declines_lands_on_the_sign_in_page(
    client: httpx.AsyncClient, forge: FakeForge
) -> None:
    await client.get("/api/v1/auth/login")
    landed = await client.get("/api/v1/auth/callback", params={"error": "access_denied"})

    assert query_of(landed)["error"] == ["sign_in_denied"]


async def test_signing_out_ends_the_session(client: httpx.AsyncClient, forge: FakeForge) -> None:
    await sign_in(client, forge)

    signed_out = await client.post("/api/v1/auth/logout", headers=ORIGIN)

    assert signed_out.status_code == 204
    assert SESSION_COOKIE not in client.cookies
    assert (await client.get("/api/v1/me")).status_code == 401


async def test_signing_in_again_ends_the_previous_session(
    client: httpx.AsyncClient, forge: FakeForge
) -> None:
    await sign_in(client, forge)
    first = client.cookies[SESSION_COOKIE]
    await sign_in(client, forge)

    assert client.cookies[SESSION_COOKIE] != first
    listed = await client.get("/api/v1/me/sessions")
    assert len(listed.json()) == 1


async def test_the_register_url_follows_the_setting(client: httpx.AsyncClient) -> None:
    answer = await client.get("/api/v1/auth/register-url")
    assert answer.json() == {"url": "http://forge.test/user/sign_up"}
