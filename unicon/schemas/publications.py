"""What the save takes and answers with, and a task's publications. A save
comes back as one of two outcomes: published, with the new publication, or a
draft, with the version written and either the errors that kept it from
publishing, each at its YAML path, or what it held back while the contest
runs.
"""

from datetime import datetime
from typing import Annotated, Any, Self

from pydantic import BaseModel, BeforeValidator, model_validator

from unicon.schemas.files import Encoded


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


class FileChange(Encoded):
    """One file of a save, with the token it was read with, or null for a
    file the save creates.
    """

    path: str
    token: str | None


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
            raise ValueError("Each path may appear once in a save.")
        return self


class Published(BaseModel):
    """A save that published: the new publication's number among the task's,
    whether it changed how the task grades, and what, and the notes the save
    makes of the task beside publishing it, such as which steps it seals
    until the reveal.
    """

    number: int
    grading_changed: bool
    changes: list[str]
    notes: list[str]


class Draft(BaseModel):
    """A save kept as a draft: the version its files were written as, the
    errors that kept it from publishing, and what it held back.
    """

    version: str
    errors: list[DefinitionError]
    held_back: list[str]


SaveResult = Published | Draft
"""A save's answer: published, or kept as a draft."""
