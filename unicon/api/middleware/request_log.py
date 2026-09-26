"""One record per request: method, path, status and timing. Nothing from the
request itself goes into it: not the query string, which carries the sign-in
code and state on the callback, not the cookie, not the body.
"""

import time
from collections.abc import Awaitable, Callable, MutableMapping
from typing import Any

from forge.log import get_logger

Scope = MutableMapping[str, Any]
Message = MutableMapping[str, Any]
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]
App = Callable[[Scope, Receive, Send], Awaitable[None]]

log = get_logger(__name__)

NO_RESPONSE = 500


class RequestLog:
    """Pure ASGI, so a streaming response is recorded when it finishes."""

    def __init__(self, app: App) -> None:
        self._app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        started = time.perf_counter()
        status = NO_RESPONSE

        async def record_status(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = int(message["status"])
            await send(message)

        try:
            await self._app(scope, receive, record_status)
        finally:
            log.info(
                "http.request",
                method=scope["method"],
                path=scope["path"],
                status=status,
                duration_ms=round((time.perf_counter() - started) * 1000, 1),
            )
