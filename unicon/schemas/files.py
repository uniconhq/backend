"""What the file routes take and answer with. A file's content travels as
text: as it is when its bytes are UTF-8, and in base64 when they are not, so
a binary file makes the same round trip as a text one. The token a file is
read with goes back with the write, and none creates the file. A folder's
entries and the history go out as the forge's own `TreeEntry` and `Change`.
"""

import base64
import binascii
from typing import Literal, Self

from forge.api.files import File as FileRecord
from forge.api.types import ConflictToken
from pydantic import BaseModel, model_validator

Encoding = Literal["utf-8", "base64"]


class Encoded(BaseModel):
    """File content as text, which must decode as its `encoding` says."""

    encoding: Encoding = "utf-8"
    content: str

    @model_validator(mode="after")
    def _decodes(self) -> Self:
        self.data()
        return self

    def data(self) -> bytes:
        if self.encoding == "base64":
            try:
                return base64.b64decode(self.content, validate=True)
            except binascii.Error as exc:
                raise ValueError("The content is not valid base64.") from exc
        return self.content.encode("utf-8")


def token_of(value: str | None) -> ConflictToken | None:
    return ConflictToken(value) if value is not None else None


class FileContent(BaseModel):
    """One file at one version, with the token a write presents back."""

    path: str
    encoding: Encoding
    content: str
    token: str

    @classmethod
    def of(cls, file: FileRecord) -> FileContent:
        encoding: Encoding
        try:
            encoding, content = "utf-8", file.content.decode("utf-8")
        except UnicodeDecodeError:
            encoding, content = "base64", base64.b64encode(file.content).decode("ascii")
        return cls(path=file.path, encoding=encoding, content=content, token=str(file.token))


class WriteFile(Encoded):
    """One file written, `token` being the one it was read with or null for
    a new file. For a task this is a save, and `confirm` and
    `keep_as_draft` do what they do for one.
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
