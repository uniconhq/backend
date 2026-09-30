"""The door the forge pushes an org's events through, at forge's
`EVENTS_PATH`. The forge calls it inside the stack, at the platform's
internal URL, with no session and no browser, so the Origin check lets
exactly this path through and the signature over the body is what admits a
request. A request whose signature does not match, or that names an org
with no secret, is refused as `forbidden` either way. A body over 1 MiB is
refused as `payload_too_large` before more of it is read, whether its
`Content-Length` says so or it runs past that with no length or a length
that is not a number, since nothing checks who sent it until it is read. An
event that is let in is answered 204 and does nothing else.
"""

from fastapi import APIRouter, Request, Response, status
from forge.api import events
from forge.api.types import OrgName

from unicon.api import raw

NO_CONTENT = status.HTTP_204_NO_CONTENT
MAX_BODY = 1024 * 1024

router = APIRouter(prefix=events.EVENTS_PATH, tags=["events"])


@router.post(
    "/{org}",
    operation_id="receiveForgeEvent",
    summary="An event the forge pushes for an org",
    status_code=NO_CONTENT,
)
async def receive_forge_event(request: Request, org: str) -> Response:
    """The signature is the hex HMAC-SHA256 of the raw body under the org's
    secret, in the first of forge's signature headers the request carries,
    `X-Forgejo-Signature` and then `X-Gitea-Signature`.
    """
    body = await raw.body(request, MAX_BODY, "An event's body")
    signature = next(
        (request.headers[name] for name in events.SIGNATURE_HEADERS if name in request.headers),
        "",
    )
    await events.check(OrgName(org), body, signature)
    return Response(status_code=NO_CONTENT)
