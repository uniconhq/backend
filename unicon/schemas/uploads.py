"""What the upload routes take and answer with. A file goes from the browser
straight to the object store: the browser asks for a slot, sends the bytes
where the slot says, and then says they are there. A slot is one of two
kinds, told apart by `method`: `post`, a form sent in one request, or
`multipart`, a URL for each part of a larger file.
"""

import uuid
from datetime import datetime
from typing import Annotated, Literal

from forge.api.uploads import PartsSlot, PostSlot
from forge.api.uploads import SlotPart as SlotPartRecord
from forge.api.uploads import Upload as UploadRecord
from pydantic import BaseModel, Field

UploadStatus = Literal["presigned", "verified", "rejected", "consumed", "expired"]


class UploadRequest(BaseModel):
    """One file to upload for the task's contestant input `input`: its name,
    the name it is committed under, its size in bytes and, when the browser
    knows it, its content type.
    """

    input: str
    filename: str
    size: int
    content_type: str | None = None


class PostUploadSlot(BaseModel):
    """A slot for a file sent in one request: a form posted to `url` with
    `fields` sent as they are and before the file, which works until
    `expires_at`.
    """

    id: uuid.UUID
    method: Literal["post"]
    url: str
    fields: dict[str, str]
    expires_at: datetime

    @classmethod
    def of(cls, slot: PostSlot) -> PostUploadSlot:
        return cls(
            id=slot.id,
            method="post",
            url=slot.url,
            fields=dict(slot.fields),
            expires_at=slot.expires_at,
        )


class UploadPart(BaseModel):
    """One part of a file sent in parts: its number, from 1, and the URL it
    is sent to with a PUT, which takes exactly its share of the file.
    """

    number: int
    url: str

    @classmethod
    def of(cls, part: SlotPartRecord) -> UploadPart:
        return cls(number=part.number, url=part.url)


class MultipartUploadSlot(BaseModel):
    """A slot for a file sent in parts: every part but the last is
    `part_size` bytes, each sent to its own URL, until `expires_at`.
    """

    id: uuid.UUID
    method: Literal["multipart"]
    part_size: int
    parts: list[UploadPart]
    expires_at: datetime

    @classmethod
    def of(cls, slot: PartsSlot) -> MultipartUploadSlot:
        return cls(
            id=slot.id,
            method="multipart",
            part_size=slot.part_size,
            parts=[UploadPart.of(part) for part in slot.parts],
            expires_at=slot.expires_at,
        )


UploadSlot = Annotated[PostUploadSlot | MultipartUploadSlot, Field(discriminator="method")]


def upload_slot(slot: PostSlot | PartsSlot) -> PostUploadSlot | MultipartUploadSlot:
    """The answer for a slot, whichever of the two kinds it is."""
    if isinstance(slot, PostSlot):
        return PostUploadSlot.of(slot)
    return MultipartUploadSlot.of(slot)


class FinishedPart(BaseModel):
    """A part the browser sent: its number and the `ETag` the store answered
    its PUT with.
    """

    number: int
    etag: str


class CompleteUploadRequest(BaseModel):
    """Every part of a file sent in parts, once each and in order. A file
    sent in one request has none.
    """

    parts: list[FinishedPart] = []


class Upload(BaseModel):
    """Where one upload stands: the input it is for, its name and content
    type, the size declared and, once measured, the size and SHA-256 in hex
    of what arrived. `verified` is an upload a submit may name; `rejected`
    is one whose size is not the one declared, which never is.
    """

    id: uuid.UUID
    input: str
    filename: str
    content_type: str | None
    declared_size: int
    size: int | None
    sha256: str | None
    status: UploadStatus

    @classmethod
    def of(cls, upload: UploadRecord) -> Upload:
        return cls(
            id=upload.id,
            input=upload.input,
            filename=upload.filename,
            content_type=upload.content_type,
            declared_size=upload.declared_size,
            size=upload.size,
            sha256=upload.sha256,
            status=upload.status.value,
        )
