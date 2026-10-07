"""What the file routes take and answer with. A file's content travels as
text: as it is when its bytes are UTF-8, and in base64 when they are not, so
a binary file makes the same round trip as a text one. A task's file may
instead be a file the organiser uploaded, named by its upload, and is read
back with `upload`, the size and digest of what it holds. The token a file
is read with goes back with the write, and none creates the file. A
folder's entries and the history go out as the forge's own `TreeEntry`, an
upload's carrying the same `upload`, and `Change`.
"""

import base64
import binascii
import uuid
from typing import Literal, Self

from forge.api.files import File as FileRecord
from forge.api.files import UploadInfo
from forge.api.types import ConflictToken, Uploaded
from pydantic import BaseModel, model_validator

Encoding = Literal["utf-8", "base64"]


def _decoded(encoding: Encoding, content: str) -> bytes:
    if encoding == "base64":
        try:
            return base64.b64decode(content, validate=True)
        except binascii.Error as exc:
            raise ValueError("The content is not valid base64.") from exc
    return content.encode("utf-8")


class Encoded(BaseModel):
    """File content as text, which must decode as its `encoding` says."""

    encoding: Encoding = "utf-8"
    content: str

    @model_validator(mode="after")
    def _decodes(self) -> Self:
        self.data()
        return self

    def data(self) -> bytes:
        return _decoded(self.encoding, self.content)


class EncodedOrUploaded(BaseModel):
    """A task's file as a save writes it: content as text, which must decode
    as its `encoding` says, or `upload`, the id of a file the organiser
    uploaded for this path, whose pointer the save writes. Exactly one of
    `content` and `upload`.
    """

    encoding: Encoding = "utf-8"
    content: str | None = None
    upload: uuid.UUID | None = None

    @model_validator(mode="after")
    def _one_of_content_and_upload(self) -> Self:
        if (self.content is None) == (self.upload is None):
            raise ValueError("Give the content or an upload, one of the two.")
        self.edit_content()
        return self

    def edit_content(self) -> bytes | Uploaded:
        if self.upload is not None:
            return Uploaded(self.upload)
        assert self.content is not None
        return _decoded(self.encoding, self.content)


def token_of(value: str | None) -> ConflictToken | None:
    return ConflictToken(value) if value is not None else None


class FileContent(BaseModel):
    """One file at one version, with the token a write presents back, and
    `upload` when it is a file an organiser uploaded: its `content` is then
    the pointer to the bytes, never opened as text, and `upload` the size
    and SHA-256 of what it holds. A typed file has none.
    """

    path: str
    encoding: Encoding
    content: str
    token: str
    upload: UploadInfo | None

    @classmethod
    def of(cls, file: FileRecord) -> FileContent:
        encoding: Encoding
        try:
            encoding, content = "utf-8", file.content.decode("utf-8")
        except UnicodeDecodeError:
            encoding, content = "base64", base64.b64encode(file.content).decode("ascii")
        return cls(
            path=file.path,
            encoding=encoding,
            content=content,
            token=str(file.token),
            upload=file.upload,
        )


class WriteFile(Encoded):
    """One file written, `token` being the one it was read with or null for
    a new file. For a task this is a save, and `confirm` and
    `keep_as_draft` do what they do for one.
    """

    token: str | None
    message: str | None = None
    confirm: bool = False
    keep_as_draft: bool = False


class WriteTaskFile(EncodedOrUploaded):
    """One file of a task written, as a save: typed content or an upload
    made for this path, `token` being the one it was read with or null for
    a new file, and `confirm` and `keep_as_draft` doing what they do for a
    save.
    """

    token: str | None
    message: str | None = None
    confirm: bool = False
    keep_as_draft: bool = False


class RollbackFile(BaseModel):
    """Write the file as it was at `version` back as a new change, `token`
    being the one of the file as it is now.
    """

    version: str
    token: str | None
    message: str | None = None
    confirm: bool = False
    keep_as_draft: bool = False


class Written(BaseModel):
    """A contest's file written: the version the change made."""

    version: str
