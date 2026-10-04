"""The two questions the proxy asks before it lets a person's bytes through,
one for each direction.

**Uploads.** A browser sends a file to `/-/uploads/<id>` on this host. Before
nginx reads a byte of the body it makes a side request here, carrying the
browser's headers and none of its body (`auth_request`). This route answers
204 and two headers when that upload may start: where at the forge the bytes
go, and what credential to present there. nginx puts the body through to that
path with that credential in place of whatever the browser sent, so the
browser never sees either, and the forge checks the person's own write access
to the repository as it hashes what arrives.

**Downloads.** A browser asks for one file of one of its own submissions at
`/-/downloads/<org>/<contest>/<task>/<number>/<path>`. nginx asks here the
same way, and the answer is where at the forge that file is read whole, what
credential to present there, and how the download is named. nginx streams
the forge's answer to the browser, so a file of any size passes through the
proxy and never through this process, and a range or a resumed download is
the forge's to answer.

Three things keep these routes to themselves. The proxy never routes them
from outside, they are left out of the OpenAPI document, and the only thing
they answer to is a session cookie for the upload's own owner or the
submission's own contestant. Everything else is 403 with no reason.
"""

import uuid
from typing import Annotated
from urllib.parse import quote, unquote

from fastapi import APIRouter, Header, Response, status
from forge.api import names, submissions, tasks, uploads
from forge.api.errors import Forbidden, NotFound

from unicon.api.deps import CurrentSession
from unicon.api.v1.submissions import NUMBER_MAX

PATH = "/-/uploads/door"
DOWNLOAD_PATH = "/-/downloads/door"
DOWNLOADS = "/-/downloads/"
PATH_HEADER = "X-Forge-Path"
AUTHORIZATION_HEADER = "X-Forge-Authorization"
DISPOSITION_HEADER = "X-Download-Disposition"
REFUSED = "That upload cannot be sent."
DOWNLOAD_REFUSED = "That file cannot be downloaded."

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


@router.get(DOWNLOAD_PATH, status_code=status.HTTP_204_NO_CONTENT)
async def download_door(
    session: CurrentSession,
    response: Response,
    original_uri: Annotated[str, Header(alias="X-Original-URI")] = "",
) -> None:
    """Whether this file may be downloaded by the caller, and if so where it
    is read from and what it is called.
    """
    org, contest, task, number, path = _download_of(original_uri)
    try:
        scope = await names.scope_at(org, contest, task)
        door = await submissions.download(session, tasks.task_id_of(scope), number, path)
    except NotFound:
        raise Forbidden(DOWNLOAD_REFUSED) from None
    response.headers[PATH_HEADER] = door.path
    response.headers[AUTHORIZATION_HEADER] = door.authorization
    response.headers[DISPOSITION_HEADER] = attachment(path)


def attachment(path: str) -> str:
    """A download named after the file's own name, the last segment of its
    path, quoted for the header when it is not plain.
    """
    name = path.rsplit("/", 1)[-1]
    quoted = quote(name, safe="")
    if quoted == name:
        return f'attachment; filename="{name}"'
    return f"attachment; filename*=UTF-8''{quoted}"


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


def _number(part: str) -> bool:
    """Whether a segment is a submission's number, in the range the API's
    own routes take, so a number no submission can have is refused before
    forge is asked.
    """
    return (
        part.isascii()
        and part.isdigit()
        and len(part) <= len(str(NUMBER_MAX))
        and 1 <= int(part) <= NUMBER_MAX
    )


def _download_of(original_uri: str) -> tuple[str, str, str, int, str]:
    """The org, contest and task names, the submission's number and the
    file's path the browser's request names, each segment decoded on its own,
    so an encoded slash stays inside its segment. Whether that file is the
    caller's to read is the forge's question; this only reads the address.
    """
    raw = original_uri.split("?", 1)[0]
    if not raw.startswith(DOWNLOADS):
        raise Forbidden(DOWNLOAD_REFUSED)
    parts = raw.removeprefix(DOWNLOADS).split("/")
    if len(parts) < 5 or not _number(parts[3]):
        raise Forbidden(DOWNLOAD_REFUSED)
    try:
        org, contest, task = (unquote(part, errors="strict") for part in parts[:3])
        path = "/".join(unquote(part, errors="strict") for part in parts[4:])
    except UnicodeDecodeError:
        raise Forbidden(DOWNLOAD_REFUSED) from None
    return org, contest, task, int(parts[3]), path
