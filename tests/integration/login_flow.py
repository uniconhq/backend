"""The three hops of a login, as the browser makes them: start at Unicon, consent
at Forgejo, come back. The two clients are the same browser, one pointed at the
app and one at the forge.
"""

import httpx


async def start(client: httpx.AsyncClient, next_path: str = "/") -> httpx.Response:
    return await client.get("/api/v1/auth/login", params={"next": next_path})


async def consent(browser: httpx.AsyncClient, started: httpx.Response) -> httpx.Response:
    return await browser.get(started.headers["location"])


async def log_in(
    client: httpx.AsyncClient, browser: httpx.AsyncClient, next_path: str = "/"
) -> httpx.Response:
    """Returns the callback response, which carries the session cookie."""
    approved = await consent(browser, await start(client, next_path))
    return await client.get(approved.headers["location"])
