"""The question the proxy asks before it lets one upload's bytes through.

A browser sends a file to `/-/uploads/<id>` on this host. Before nginx reads
a byte of the body it makes a side request here, carrying the browser's
headers and none of its body (`auth_request`). This route answers 204 and
two headers when that upload may start: where at the forge the bytes go, and
what credential to present there. nginx puts the body through to that path
with that credential in place of whatever the browser sent, so the browser
never sees either, and the forge checks the person's own write access to the
repository as it hashes what arrives.

Three things keep this route to itself. The proxy never routes it from
outside, it is left out of the OpenAPI document, and the only thing it
answers to is a session cookie for the upload's own owner. Everything else
is 403 with no reason; the browser learns where its upload stands by asking
for the upload, not by reading this.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Header, Response, status
from forge.api import uploads
from forge.api.errors import Forbidden

from unicon.api.deps import CurrentSession

PATH = "/-/uploads/door"
PATH_HEADER = "X-Forge-Path"
AUTHORIZATION_HEADER = "X-Forge-Authorization"
REFUSED = "That upload cannot be sent."

router = APIRouter(include_in_schema=False)


@router.get(PATH, status_code=status.HTTP_204_NO_CONTENT)
async def upload_door(
    session: CurrentSession,
    response: Response,
    original_uri: Annotated[str, Header(alias="X-Original-URI")] = "",
    upload_length: Annotated[str, Header(alias="X-Upload-Length")] = "",
) -> None:
    """Whether this upload may start, and if so where its bytes go."""
    door = await uploads.door(session, _upload_of(original_uri), length=_length_of(upload_length))
    response.headers[PATH_HEADER] = door.path
    response.headers[AUTHORIZATION_HEADER] = door.authorization


def _upload_of(original_uri: str) -> uuid.UUID:
    """The upload the browser's request names. The proxy matches the shape
    of the path before it asks, so anything else here is a request that did
    not come through it.
    """
    path = original_uri.split("?", 1)[0]
    try:
        return uuid.UUID(path.rsplit("/", 1)[-1])
    except ValueError:
        raise Forbidden(REFUSED) from None


def _length_of(upload_length: str) -> int:
    """How many bytes the browser says it is sending. A request with no
    length, or one that is not a number, sends nothing this route will
    vouch for.
    """
    if not upload_length.isascii() or not upload_length.isdigit():
        raise Forbidden(REFUSED)
    return int(upload_length)
