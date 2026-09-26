"""A state-changing request carrying the session cookie must say it came from
the platform's own origin, in `Origin` or, failing that, in `Referer`. Reads
and requests without the cookie are not checked.
"""

from collections.abc import Awaitable, Callable, MutableMapping
from http.cookies import SimpleCookie
from typing import Any
from urllib.parse import urlsplit

from forge.domain.errors import UniconError

from unicon.api.cookies import SESSION_COOKIE
from unicon.api.errors import problem_response, status_of
from unicon.schemas.problem import Problem

Scope = MutableMapping[str, Any]
Message = MutableMapping[str, Any]
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]
App = Callable[[Scope, Receive, Send], Awaitable[None]]

UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


class OriginMismatch(UniconError):
    code = "origin_mismatch"


class OriginCheck:
    """Pure ASGI, so streaming responses and background work pass through it
    untouched.
    """

    def __init__(self, app: App, public_url: str) -> None:
        self._app = app
        self._expected = _origin_of(public_url)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and self._is_forgeable(scope):
            headers = _headers(scope)
            if _claimed_origin(headers) != self._expected:
                error = OriginMismatch("This request did not come from the site.")
                status = status_of(error)
                response = problem_response(
                    Problem.of(
                        code=error.code, status=status, title="Forbidden", detail=error.detail
                    )
                )
                await response(scope, receive, send)
                return
        await self._app(scope, receive, send)

    def _is_forgeable(self, scope: Scope) -> bool:
        if scope["method"] not in UNSAFE_METHODS:
            return False
        cookies: SimpleCookie = SimpleCookie()
        cookies.load(_headers(scope).get("cookie", ""))
        return SESSION_COOKIE in cookies


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
