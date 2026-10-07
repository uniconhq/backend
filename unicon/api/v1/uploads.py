"""A person's files on their way into a repository at the forge. The browser
works out the file's digest, asks for a slot, sends the bytes to the address
the slot names, and says when they are there; forge asks the forge whether
the place holds them.

A contestant's slot, for one of the task's contestant inputs, needs a
session and no role: forge checks that the caller may submit to the task
now. An organiser's slot, for a file they put into the task at a path, needs
the manager role at the task, and the next save that names the upload
writes the pointer to it there. Both are completed by the same route, which
needs a session alone, since an upload is its owner's alone, for one task,
and anyone else's is no such upload.

The bytes themselves go through the upload door and never through here
(`unicon.api.door`).
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status
from forge.api import tasks, uploads
from forge.api.access import Organiser
from forge.api.types import Role, ScopeKind

from unicon.api.deps import CurrentSession
from unicon.api.guard import PREFIX, TaskAtPath, require
from unicon.schemas.uploads import TaskFileUploadRequest, Upload, UploadRequest, UploadSlot

CREATED = status.HTTP_201_CREATED
TASK = PREFIX[ScopeKind.TASK]

router = APIRouter(prefix=TASK, tags=["submissions"])

TaskManager = Annotated[Organiser, Depends(require(Role.MANAGER, ScopeKind.TASK))]


@router.post(
    "/uploads",
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
    "/organise/uploads",
    operation_id="requestTaskFileUploadSlot",
    summary="Ask for a slot to upload one file into the task at a path",
    status_code=CREATED,
    response_model=UploadSlot,
    tags=["files"],
)
async def request_task_file_upload_slot(
    organiser: TaskManager, body: TaskFileUploadRequest
) -> uploads.Slot:
    """The address to send the file to, or `ready` for a file the task's
    place at the forge already holds. Nothing is in the task until a save
    names the upload for the same path. A path that leaves the task is
    `invalid_path`, and a name, digest or size that is not one
    `invalid_inputs`, naming the path.
    """
    return await uploads.task_file_slot(
        organiser,
        tasks.task_id_of(organiser.scope),
        path=body.path,
        size=body.size,
        sha256=body.sha256,
        content_type=body.content_type,
    )


@router.post(
    "/uploads/{upload}/complete",
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
    as declared or did not arrive. Asked again, it answers the same. A
    contestant's upload and an organiser's are completed alike.
    """
    return await uploads.complete(session, tasks.task_id_of(scope), upload)
