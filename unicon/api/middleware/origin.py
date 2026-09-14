"""The other half of the CSRF story. A state-changing request carrying the session
cookie must say it came from this site. Requests without the cookie are not
checked: there is nothing to forge.
"""

from collections.abc import Awaitable, Callable
from urllib.parse import urlsplit

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from unicon.api.cookies import SESSION_COOKIE
from unicon.api.errors import problem_response
from unicon.domain.errors import OriginMismatch
from unicon.schemas.problem import Problem

UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


class OriginCheck(BaseHTTPMiddleware):
    def __init__(self, app: Callable[..., Awaitable[None]], public_url: str) -> None:
        super().__init__(app)
        self._expected = _origin_of(public_url)

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        if self._is_forgeable(request) and _claimed_origin(request) != self._expected:
            error = OriginMismatch("This request did not come from the site.")
            return problem_response(
                Problem.of(
                    code=error.code,
                    status=error.status,
                    title="Forbidden",
                    detail=error.detail,
                )
            )
        return await call_next(request)

    def _is_forgeable(self, request: Request) -> bool:
        return request.method in UNSAFE_METHODS and SESSION_COOKIE in request.cookies


def _claimed_origin(request: Request) -> str | None:
    """`Origin`, or the origin part of `Referer` where the browser sends no
    `Origin`.
    """
    origin = request.headers.get("origin")
    if origin:
        return origin
    referer = request.headers.get("referer")
    return _origin_of(referer) if referer else None


def _origin_of(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}"
