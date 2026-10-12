"""What the save takes and answers with, and a task's publications. A save
comes back as one of two outcomes: published, with the new publication, or a
draft, with the version written and either the errors that kept it from
publishing, each at its YAML path, or what it held back while the contest
runs.
"""

import uuid
from datetime import datetime
from typing import Annotated, Any, Self

from forge.api.types import Uploaded
from pydantic import BaseModel, BeforeValidator, model_validator

from unicon.schemas.files import Encoding, written_content


class DefinitionError(BaseModel):
    """One thing wrong with a definition file: its YAML path, "" for the file
    as a whole, and a sentence a form shows beside that field.
    """

    path: str
    message: str


def _number_of(publication: Any) -> Any:
    """A publication's number among its task's, from the forge's id for it,
    which is built from the keys the task is filed under and stays home.
    """
    if isinstance(publication, str) and "#" in publication:
        return int(publication.rsplit("#", 1)[1])
    return publication


PublicationNumber = Annotated[int, BeforeValidator(_number_of)]
"""A publication by its number among its task's publications."""


class Publication(BaseModel):
    """One publication: its number among the task's publications, the version
    it froze, whether it changed how the task grades and what, and when.
    Which workflow each of its workflow names was at the forge stays out.
    """

    number: int
    version: str
    grading_changed: bool
    changes: list[str]
    at: datetime


class FileChange(BaseModel):
    """One file of a save, with the token it was read with: typed as
    `content`, uploaded for this path as `upload`, or removed with `remove:
    true`, exactly one of the three. The token is null for a file the save
    creates, and a removal always carries one. Removing a folder, such as a
    test, is removing each file under it, named one by one.
    """

    path: str
    token: str | None
    encoding: Encoding = "utf-8"
    content: str | None = None
    upload: uuid.UUID | None = None
    remove: bool = False

    @model_validator(mode="after")
    def _written_or_removed(self) -> Self:
        if self.remove:
            if self.content is not None or self.upload is not None:
                raise ValueError("A file being removed cannot also have content or an upload.")
            if self.token is None:
                raise ValueError("To remove a file, say which version of it was read.")
        self.edit_content()
        return self

    def edit_content(self) -> bytes | Uploaded | None:
        """What the save writes at the path, or none to remove the file."""
        if self.remove:
            return None
        return written_content(self.encoding, self.content, self.upload)


class SaveRequest(BaseModel):
    """The files a save writes, several at once. `keep_as_draft` writes them
    as a draft that says what it held back and publishes nothing, on any
    save. Otherwise, while the task's contest runs, `confirm` publishes a
    change to how the task grades; an empty save with `confirm` publishes a
    draft kept earlier.
    """

    changes: list[FileChange] = []
    confirm: bool = False
    keep_as_draft: bool = False
    message: str | None = None

    @model_validator(mode="after")
    def _one_change_per_path(self) -> Self:
        paths = [change.path for change in self.changes]
        if len(set(paths)) != len(paths):
            raise ValueError("Each file can appear only once in a save.")
        return self


class Published(BaseModel):
    """A save that published: the new publication's number among the task's,
    whether it changed how the task grades, and what, the notes the save
    makes of the task beside publishing it, such as which steps it seals
    until the reveal, and how many submissions it `regraded`, queued to be
    graded again against it.
    """

    number: int
    grading_changed: bool
    changes: list[str]
    notes: list[str]
    regraded: int


class Draft(BaseModel):
    """A save kept as a draft: the version its files were written as, the
    errors that kept it from publishing, and what it held back.
    """

    version: str
    errors: list[DefinitionError]
    held_back: list[str]


SaveResult = Published | Draft
"""A save's answer: published, or kept as a draft."""
