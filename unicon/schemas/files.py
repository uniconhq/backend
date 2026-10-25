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
from typing import Any, Literal, Self

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
        self.edit_content()
        return self

    def edit_content(self) -> bytes | Uploaded:
        return written_content(self.encoding, self.content, self.upload)


def written_content(
    encoding: Encoding, content: str | None, upload: uuid.UUID | None
) -> bytes | Uploaded:
    """What a task's file is written as: the decoded `content`, or the
    `upload` it names. `ValueError` unless exactly one of the two is given,
    or for content that does not decode as its `encoding` says.
    """
    if (content is None) == (upload is None):
        raise ValueError("Give the content or an upload, one of the two.")
    if upload is not None:
        return Uploaded(upload)
    assert content is not None
    return _decoded(encoding, content)


def token_of(value: str | None) -> ConflictToken | None:
    return ConflictToken(value) if value is not None else None


class FileContent(BaseModel):
    """One file at one version, with the token a write presents back, and
    `upload` when it is a file an organiser uploaded: its `content` is then
    the pointer to the bytes, never opened as text, and `upload` the size
    and SHA-256 of what it holds. A typed file has none. `version` is the
    commit holding the file as read, the latest change to it or the one it
    was read at, which a task's file is downloaded at
    (`/-/downloads/<org>/<contest>/<task>/versions/<version>/<path>`); null
    when the forge names no commit and it was not read at one. A tree's
    entries name their `version` the same way.
    """

    path: str
    encoding: Encoding
    content: str
    token: str
    upload: UploadInfo | None
    version: str | None

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
            version=file.version,
        )


class WriteFile(Encoded):
    """One file written, `token` being the one it was read with or null for
    a new file. For a task this is a save, and `confirm`, `asked` and
    `keep_as_draft` do what they do for one.
    """

    token: str | None
    message: str | None = None
    confirm: bool = False
    asked: str | None = None
    keep_as_draft: bool = False

    @model_validator(mode="before")
    @classmethod
    def _no_upload(cls, given: Any) -> Any:
        # A contest's file takes typed content alone; an upload named beside
        # it is refused rather than dropped.
        if isinstance(given, dict) and "upload" in given:
            raise ValueError("A contest's file cannot be an upload.")
        return given


class WriteTaskFile(EncodedOrUploaded):
    """One file of a task written, as a save: typed content or an upload
    made for this path, `token` being the one it was read with or null for
    a new file, and `confirm`, `asked` and `keep_as_draft` doing what they
    do for a save.
    """

    token: str | None
    message: str | None = None
    confirm: bool = False
    asked: str | None = None
    keep_as_draft: bool = False


class RollbackFile(BaseModel):
    """Write the file as it was at `version` back as a new change, `token`
    being the one of the file as it is now, and, for a task, `confirm`,
    `asked` and `keep_as_draft` doing what they do for a save.
    """

    version: str
    token: str | None
    message: str | None = None
    confirm: bool = False
    asked: str | None = None
    keep_as_draft: bool = False


class Written(BaseModel):
    """A contest's file written: the version the change made, and, for
    `contest.yaml`, each leaderboard's `notes` on the tasks it covers, such as one
    that counts nothing from a task, the notes the organisers' reading of
    the leaderboards carries beside each.
    """

    version: str
    notes: list[str]
