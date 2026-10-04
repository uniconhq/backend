"""What the upload routes take and answer with. A file goes from the browser
straight into the forge's large-file store through the upload door: the
browser works out its SHA-256, asks for a slot, sends the bytes to the
address the slot names, and then says they are there.
"""

import uuid

from forge.api.uploads import Slot, UploadStatus
from pydantic import BaseModel


class UploadRequest(BaseModel):
    """One file to upload for the task's contestant input `input`: the name
    it is committed under, its size in bytes, the SHA-256 of its content in
    lowercase hex and, when the browser knows it, its content type.

    The digest is what the forge checks the bytes against as they arrive, so
    a file that changed between being read and being sent is refused there
    rather than committed.
    """

    input: str
    filename: str
    size: int
    sha256: str
    content_type: str | None = None


UploadSlot = Slot
"""A slot, the forge's own record."""


class Upload(BaseModel):
    """Where one upload stands: the input it is for, its name and content
    type, the size and digest declared for it, and its status. `verified` is
    an upload a submit may name.
    """

    id: uuid.UUID
    input: str
    filename: str
    content_type: str | None
    size: int
    sha256: str
    status: UploadStatus
