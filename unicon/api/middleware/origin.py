"""Every state-changing request must say it came from the platform's own
origin, in `Origin` or, failing that, in `Referer`. Reads are not checked.
Whether the request carries a session makes no difference: the check runs
before anything looks at the cookie, so a cookie the parser cannot read
cannot hide a session from it, and a route that changes state without a
session is covered the day it exists. The platform's origin is asked of
forge on the first request that is checked, not when the app is built, so an
app forge was never started for can still be built.

One path is let through: the door the forge pushes an org's events to,
forge's `EVENTS_PATH` followed by the org's name. The forge calls it from
inside the stack with no browser and no session, so it has no origin to
claim, and the signature over the body is what admits it.
"""

from urllib.parse import urlsplit

from forge.api import public_url
from forge.api.errors import UniconError
from forge.api.events import EVENTS_PATH
from starlette.types import ASGIApp, Receive, Scope, Send

from unicon.api.errors import problem_for

UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


class OriginMismatch(UniconError):
    code = "origin_mismatch"


class OriginCheck:
    """Pure ASGI, so streaming responses and background work pass through it
    untouched.
    """

    def __init__(self, app: ASGIApp) -> None:
        self._app = app
        self._expected: str | None = None

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if _is_checked(scope) and _claimed_origin(_headers(scope)) != self._origin():
            error = OriginMismatch("This request did not come from the site.")
            await problem_for(error)(scope, receive, send)
            return
        await self._app(scope, receive, send)

    def _origin(self) -> str:
        if self._expected is None:
            self._expected = _origin_of(public_url())
        return self._expected


def _is_checked(scope: Scope) -> bool:
    return (
        scope["type"] == "http"
        and scope["method"] in UNSAFE_METHODS
        and not _is_forge_event(scope["path"])
    )


def _is_forge_event(path: str) -> bool:
    """A push from the forge: one org name after the events path, and
    nothing more.
    """
    org = path.removeprefix(f"{EVENTS_PATH}/")
    return org != path and org != "" and "/" not in org


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
