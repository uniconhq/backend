"""One HTTP client for every call to Forgejo. Concurrency is capped at eight:
above that Forgejo's latency climbs without any more work getting done.
"""

import asyncio
from types import TracebackType

import httpx

from unicon.forge.errors import ForgeRejected, ForgeUnreachable
from unicon.settings import Settings

CONCURRENT_CALLS = 8
TIMEOUT = httpx.Timeout(10.0, connect=5.0)
SERVER_ERROR = 500


class ForgeHttp:
    """Shared by both clients and closed with the app."""

    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client
        self._in_flight = asyncio.Semaphore(CONCURRENT_CALLS)

    async def request(self, method: str, path: str, **kwargs: object) -> httpx.Response:
        async with self._in_flight:
            try:
                response = await self._client.request(method, path, **kwargs)  # type: ignore[arg-type]
            except httpx.HTTPError as exc:
                raise ForgeUnreachable(str(exc)) from exc
        if response.status_code >= SERVER_ERROR:
            raise ForgeUnreachable(f"Forgejo answered {response.status_code}")
        if response.is_error:
            raise ForgeRejected(response.status_code, response.text)
        return response

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> ForgeHttp:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self.aclose()


def new_forge_http(settings: Settings) -> ForgeHttp:
    base_url = str(settings.forge_internal_url).rstrip("/")
    return ForgeHttp(httpx.AsyncClient(base_url=base_url, timeout=TIMEOUT))
