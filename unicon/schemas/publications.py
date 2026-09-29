"""What the save takes and answers with, and a task's publications. A save
comes back as one of two outcomes, told apart by `outcome`: `published`,
with the new publication, or `draft`, with the version written and either
the errors that kept it from publishing, each at its YAML path, or what it
held back while the contest runs.
"""

from datetime import datetime
from typing import Annotated, Literal, Self

from forge.api.publications import Draft, Published, Registration
from forge.api.publications import Publication as PublicationRecord
from forge.api.types import Problem
from pydantic import BaseModel, Field, model_validator

from unicon.schemas.files import Encoded


class DefinitionError(BaseModel):
    """One thing wrong with a definition file: its YAML path, "" for the file
    as a whole, and a sentence a form shows beside that field.
    """

    path: str
    message: str

    @classmethod
    def of(cls, problem: Problem) -> DefinitionError:
        return cls(path=problem["path"], message=problem["message"])


class Publication(BaseModel):
    """One publication: its number among the task's publications, the version
    it froze, whether it changed how the task grades and what, and when.
    """

    id: str
    number: int
    version: str
    grading_changed: bool
    changes: list[str]
    at: datetime

    @classmethod
    def of(cls, publication: PublicationRecord) -> Publication:
        return cls(
            id=publication.id,
            number=publication.number,
            version=publication.version,
            grading_changed=publication.grading_changed,
            changes=list(publication.changes),
            at=publication.at,
        )


class FileChange(Encoded):
    """One file of a save, with the token it was read with, or null for a
    file the save creates.
    """

    path: str
    token: str | None


class SaveRequest(BaseModel):
    """The files a save writes, several at once. While the task's contest
    runs, `confirm` publishes a change to how the task grades, and
    `keep_as_draft` writes it as a draft that says what it held back; an
    empty save with `confirm` publishes a draft kept that way.
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


class PublishedSave(BaseModel):
    """A save that published. `registration` says where the task's
    registration for grading stands: `done` by this save, `pending` with the
    poller, or `not_needed` because an earlier publication did it.
    """

    outcome: Literal["published"]
    publication: str
    number: int
    grading_changed: bool
    changes: list[str]
    registration: Registration

    @classmethod
    def of(cls, result: Published) -> PublishedSave:
        return cls(
            outcome="published",
            publication=result.publication,
            number=result.number,
            grading_changed=result.grading_changed,
            changes=list(result.changes),
            registration=result.registration,
        )


class DraftSave(BaseModel):
    """A save kept as a draft: the version its files were written as, the
    errors that kept it from publishing, and what it held back.
    """

    outcome: Literal["draft"]
    version: str
    errors: list[DefinitionError]
    held_back: list[str]

    @classmethod
    def of(cls, result: Draft) -> DraftSave:
        return cls(
            outcome="draft",
            version=result.version,
            errors=[DefinitionError.of(problem) for problem in result.errors],
            held_back=list(result.held_back),
        )


SaveResult = Annotated[PublishedSave | DraftSave, Field(discriminator="outcome")]


def save_result(result: Published | Draft) -> PublishedSave | DraftSave:
    """The answer for a save's result, whichever of the two it is."""
    if isinstance(result, Published):
        return PublishedSave.of(result)
    return DraftSave.of(result)
