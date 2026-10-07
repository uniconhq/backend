"""A person's files on their way into a repository at the forge. The browser
works out the file's digest, asks for a slot, sends the bytes to the address
the slot names, and says when they are there; forge asks the forge whether
the place holds them. Both need a session and no role: forge checks that the
caller may submit to the task now, and an upload is its owner's alone, for
one task, so anyone else's is no such upload.

The bytes themselves go through the upload door and never through here
(`unicon.api.door`).
"""

import uuid

from fastapi import APIRouter, status
from forge.api import tasks, uploads
from forge.api.types import ScopeKind

from unicon.api.deps import CurrentSession
from unicon.api.guard import PREFIX, TaskAtPath
from unicon.schemas.uploads import Upload, UploadRequest, UploadSlot

CREATED = status.HTTP_201_CREATED
TASK = PREFIX[ScopeKind.TASK]

router = APIRouter(prefix=f"{TASK}/uploads", tags=["submissions"])


@router.post(
    "",
    operation_id="requestUploadSlot",
    summary="Ask for a slot to upload one file for the task",
    status_code=CREATED,
    response_model=UploadSlot,
)
async def request_upload_slot(
    session: CurrentSession, scope: TaskAtPath, body: UploadRequest
) -> uploads.Slot:
    """The address to send the file to, or `ready` for a file the forge
    already holds, which needs no upload at all. A path the input does not
    take is `invalid_inputs` and a file over the input's `max_size`
    `too_large`, naming the limit and the input.
    """
    return await uploads.slot(
        session,
        tasks.task_id_of(scope),
        input=body.input,
        filename=body.filename,
        size=body.size,
        sha256=body.sha256,
        content_type=body.content_type,
    )


@router.post(
    "/{upload}/complete",
    operation_id="completeUpload",
    summary="Say an upload's bytes are there",
    response_model=Upload,
)
async def complete_upload(
    session: CurrentSession, scope: TaskAtPath, upload: uuid.UUID
) -> uploads.Upload:
    """Forge asks the forge whether the place holds the object: `verified`
    when it does, `upload_not_ready` when it does not. The forge keeps
    nothing that is not what its address named, so an upload either arrived
    as declared or did not arrive. Asked again, it answers the same.
    """
    return await uploads.complete(session, tasks.task_id_of(scope), upload)
