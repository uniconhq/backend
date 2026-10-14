"""What the save takes and answers with, and a task's publications. A save
comes back as one of two outcomes: published, with the new publication, or a
draft, with the version written and either the errors that kept it from
publishing, each at its YAML path, or what it held back while the contest
runs.
"""

import uuid
from datetime import datetime
from typing import Annotated, Any, Self

from forge.api.boards import Better
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


class ValueMeaning(BaseModel):
    """One value the task's workflow reports, as a page names it: its `name`
    in the report, its `title` ("Run time") and its `unit` ("ms", only on a
    number), each null where the workflow gives none, so the page names it
    by `name`; and, on a number reported for each test, which way is
    `better`, null otherwise. How a value combines across the tests is each
    board's own choice, on its key.
    """

    name: str
    title: str | None
    unit: str | None
    better: Better | None


class Publication(BaseModel):
    """One publication: its number among the task's publications, the version
    it froze, whether it changed how the task grades and what, and when;
    and `meanings`, every value its workflow reports, in the workflow's
    order, with the words it froze for each, which a form picking a value
    lists. A publication made before those words were kept lists its values
    reported for each test by name alone. Which workflow each of its
    workflow names was at the forge stays out.
    """

    number: int
    version: str
    grading_changed: bool
    changes: list[str]
    at: datetime
    meanings: list[ValueMeaning]


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
    save, which every save that would publish something new needs then; an
    empty save with `confirm` publishes a draft kept earlier. `asked` is the
    `confirmation_required`'s own: with it, the confirmation stands only
    while the head and the latest publication are the ones asked about.
    """

    changes: list[FileChange] = []
    confirm: bool = False
    asked: str | None = None
    keep_as_draft: bool = False
    message: str | None = None

    @model_validator(mode="after")
    def _one_change_per_path(self) -> Self:
        paths = [change.path for change in self.changes]
        if len(set(paths)) != len(paths):
            raise ValueError("Each file can appear only once in a save.")
        return self


class SaveEffect(BaseModel):
    """What a save does, in the words and parts a running contest's
    `confirmation_required` asks with: `summary`, "Results change." or
    "Nobody's result changes.", with `results_change` its flag; and the
    sentences under "Runs again", "Scores" and "What entrants read", each
    list holding at least one, a "nothing changes" line when nothing does.
    """

    results_change: bool
    summary: str
    runs_again: list[str]
    scores: list[str]
    reading: list[str]


class Published(BaseModel):
    """A save that published: the new publication's number among the task's,
    whether it changed how the task grades, and what, the notes the save
    makes of the task beside publishing it, such as which steps it seals
    until the reveal, how many submissions it `regraded`, queued to be
    graded again against it, and what it did, `effect`, in the words the
    question before a save in a running contest uses.
    """

    number: int
    grading_changed: bool
    changes: list[str]
    notes: list[str]
    regraded: int
    effect: SaveEffect


class Draft(BaseModel):
    """A save kept as a draft: the version its files were written as, the
    errors that kept it from publishing, and what it held back.
    """

    version: str
    errors: list[DefinitionError]
    held_back: list[str]


SaveResult = Published | Draft
"""A save's answer: published, or kept as a draft."""
