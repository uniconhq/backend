"""Cross-site requests cannot change anything. A state-changing request that
carries the session cookie but not an Origin of this site is somebody else's
page using the browser.
"""

import httpx

from tests.integration import login_flow
from tests.integration.conftest import APP_URL

ELSEWHERE = "https://evil.test"


async def test_a_request_from_another_site_is_refused(
    client: httpx.AsyncClient, browser: httpx.AsyncClient
) -> None:
    await login_flow.log_in(client, browser)

    refused = await client.post("/api/v1/auth/logout", headers={"Origin": ELSEWHERE})

    assert refused.status_code == 403
    assert refused.json()["code"] == "origin_mismatch"
    assert (await client.get("/api/v1/me")).status_code == 200


async def test_a_request_with_no_origin_at_all_is_refused(
    client: httpx.AsyncClient, browser: httpx.AsyncClient
) -> None:
    await login_flow.log_in(client, browser)

    refused = await client.post("/api/v1/auth/logout")

    assert refused.status_code == 403
    assert refused.json()["code"] == "origin_mismatch"


async def test_a_referer_from_this_site_is_enough(
    client: httpx.AsyncClient, browser: httpx.AsyncClient
) -> None:
    await login_flow.log_in(client, browser)

    accepted = await client.post("/api/v1/auth/logout", headers={"Referer": f"{APP_URL}/account"})

    assert accepted.status_code == 204


async def test_a_request_from_this_site_goes_through(
    client: httpx.AsyncClient, browser: httpx.AsyncClient
) -> None:
    await login_flow.log_in(client, browser)

    accepted = await client.post("/api/v1/auth/logout", headers={"Origin": APP_URL})

    assert accepted.status_code == 204


async def test_without_a_session_the_answer_is_401_not_403(client: httpx.AsyncClient) -> None:
    signed_out = await client.post("/api/v1/auth/logout")

    assert signed_out.status_code == 401
    assert signed_out.json()["code"] == "unauthenticated"
