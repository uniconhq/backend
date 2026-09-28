"""Every state-changing request must say it came from the platform's own
origin, in `Origin` or, failing that, in `Referer`. Reads are not checked.
Whether the request carries a session makes no difference: the check runs
before anything looks at the cookie, so a cookie the parser cannot read
cannot hide a session from it, and a route that changes state without a
session is covered the day it exists.
"""

from urllib.parse import urlsplit

from forge.domain.errors import UniconError
from starlette.types import ASGIApp, Receive, Scope, Send

from unicon.api.errors import problem_for

UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


class OriginMismatch(UniconError):
    code = "origin_mismatch"


class OriginCheck:
    """Pure ASGI, so streaming responses and background work pass through it
    untouched.
    """

    def __init__(self, app: ASGIApp, public_url: str) -> None:
        self._app = app
        self._expected = _origin_of(public_url)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if _is_state_changing(scope) and _claimed_origin(_headers(scope)) != self._expected:
            error = OriginMismatch("This request did not come from the site.")
            await problem_for(error)(scope, receive, send)
            return
        await self._app(scope, receive, send)


def _is_state_changing(scope: Scope) -> bool:
    return scope["type"] == "http" and scope["method"] in UNSAFE_METHODS


def _headers(scope: Scope) -> dict[str, str]:
    return {
        name.decode("latin-1").lower(): value.decode("latin-1")
        for name, value in scope.get("headers", [])
    }


def _claimed_origin(headers: dict[str, str]) -> str | None:
    origin = headers.get("origin")
    if origin:
        return origin
    referer = headers.get("referer")
    return _origin_of(referer) if referer else None


def _origin_of(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}"
