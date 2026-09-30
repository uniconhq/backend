"""A contestant's files on their way to a submission. The browser asks for a
slot for one file, sends the bytes straight to the object store where the
slot says, and says when they are there; forge measures what arrived. Both
need a session and no role: forge checks that the caller may submit to the
task now, and an upload is its owner's alone, for one task, so anyone else's
is no such upload.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Body, status
from forge.api import tasks, uploads
from forge.api.types import ScopeKind

from unicon.api.deps import CurrentSession
from unicon.api.guard import PREFIX, TaskAtPath
from unicon.schemas.uploads import (
    CompleteUploadRequest,
    MultipartUploadSlot,
    PostUploadSlot,
    Upload,
    UploadRequest,
    UploadSlot,
    upload_slot,
)

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
) -> PostUploadSlot | MultipartUploadSlot:
    """A form for one request, or for a file larger than forge takes in one
    request a URL for each part. A file the input does not take is `invalid_inputs` and one over
    the input's or the task's size `too_large`, naming the limit.
    """
    slot = await uploads.slot(
        session,
        tasks.task_id_of(scope),
        input=body.input,
        filename=body.filename,
        size=body.size,
        content_type=body.content_type,
    )
    return upload_slot(slot)


@router.post(
    "/{upload}/complete",
    operation_id="completeUpload",
    summary="Say an upload's bytes are there",
)
async def complete_upload(
    session: CurrentSession,
    scope: TaskAtPath,
    upload: uuid.UUID,
    body: Annotated[CompleteUploadRequest | None, Body()] = None,
) -> Upload:
    """Forge measures what arrived: `verified` when it is the size declared,
    `rejected` when it is not. A file sent in parts names every part with
    the `ETag` the store answered it with. Asked again, it answers the same.
    """
    parts = body.parts if body is not None else []
    completed = await uploads.complete(
        session,
        tasks.task_id_of(scope),
        upload,
        parts=[uploads.FinishedPart(part.number, part.etag) for part in parts],
    )
    return Upload.of(completed)
