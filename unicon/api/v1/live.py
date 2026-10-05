"""One Server-Sent Events stream per open tab of a signed-in session, carrying the nudges
forge says the session may hear and nothing else: each is an event named
by its kind, `grading`, `announcement`, `clarification` or `resync`, whose
data is one id. A page that hears one asks for the thing again through the
ordinary routes, which check the caller as for any other request, so a
stream left open in a tab is never a second way to read anything.

The stream writes a comment every fifteen seconds when there is nothing to
say, which keeps proxies from closing it and tells the server a browser has
gone. The route waits for forge to have checked the session and
subscribed before it answers, so a refusal is an ordinary error answer and
never a 200 that ends at once. It ends when the session does, or when the
same session opens more streams than forge keeps; the browser reconnects
after `retry`, and a page polls while it cannot. The proxy must not buffer it, which the
`X-Accel-Buffering` header asks of nginx on top of the proxy's own block
for this path.
"""

from collections.abc import AsyncIterator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from forge.api import live

from unicon.api.deps import CurrentSession

RETRY_MS = 5000
HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}

router = APIRouter(tags=["live"])


@router.get(
    "/live",
    operation_id="streamLiveUpdates",
    summary="The nudges the caller's session may hear, as Server-Sent Events",
    response_class=StreamingResponse,
    responses={200: {"content": {"text/event-stream": {}}}},
)
async def stream_live_updates(session: CurrentSession) -> StreamingResponse:
    """Each event is named by its kind and carries one id."""
    nudges = live.stream(session.id)
    try:
        await anext(nudges)
    except BaseException:
        await nudges.aclose()
        raise
    return StreamingResponse(_events(nudges), media_type="text/event-stream", headers=HEADERS)


async def _events(nudges: AsyncIterator[live.Nudge | None]) -> AsyncIterator[str]:
    yield f"retry: {RETRY_MS}\n\n"
    async for nudge in nudges:
        if nudge is None:
            yield ": still here\n\n"
        else:
            yield f"event: {nudge.kind.value}\ndata: {nudge.id}\n\n"
