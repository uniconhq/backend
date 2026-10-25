"""The blocks a task's values and a leaderboard's columns are built from,
as the editor reads them (SIMPLER-CORE.md 10.1, 14 and 19): each block
once, what it gives in words, and its forms, each with the inputs it takes,
the kind each one takes, where the form may be used and what it gives;
with the leaves a value and a column may hold, the facts each may read,
the word a block's `missing` takes to leave out a run or a submission and
the languages a program may be written in.
"""

from typing import Literal, Self

from forge.api import blocks
from pydantic import BaseModel

Kind = Literal[
    "number",
    "runs",
    "results",
    "submission",
    "either",
    "name",
    "directions",
    "weights",
    "missing",
    "path",
    "language",
]
"""What an input takes, or a form gives."""


class BlockInput(BaseModel):
    """One input of a form: the `kind` it takes, a number, a group's `runs`,
    a task's `results`, one `submission`'s results, `either` a number or a
    submission's results, `best_each`'s value by `name` and its
    `directions`, `weights` by a repeated input's values, what a missing
    report or input counts as, a `path`, a folder of the task such as
    `programs/mean/`, or a `language`, one of the catalogue's `languages`;
    a list of at least
    `least` and at most `most` when `least` is given (`most` null for no
    most), one node otherwise; whether it may be left out; whether its
    block reads it once for each run or result it goes over (`per_run`),
    as a fold's `of` and `where` and a pick's `where` and `by` are; and
    whether it takes a number written out alone, never a leaf or a block
    (`plain`).
    """

    kind: Kind
    least: int | None
    most: int | None
    optional: bool
    per_run: bool
    plain: bool

    @classmethod
    def of(cls, given: blocks.BlockInput) -> Self:
        return cls(
            kind=given.kind.value,
            least=given.least,
            most=given.most,
            optional=given.optional,
            per_run=given.per_run,
            plain=given.plain,
        )


class BlockForm(BaseModel):
    """One way a block is given its inputs: what it is `given`, in words,
    such as "numbers" or "a group's runs", its inputs by name, in the order
    a node writes them, where it may be used, `scope`, a task's value, a
    board's column or both, and what it `gives`: a number, one
    submission's results, or, for `otherwise`, either.
    """

    given: str
    inputs: dict[str, BlockInput]
    scope: Literal["task", "board", "both"]
    gives: Kind

    @classmethod
    def of(cls, form: blocks.Form) -> Self:
        return cls(
            given=form.given,
            inputs={name: BlockInput.of(given) for name, given in form.inputs.items()},
            scope=form.scope.value,
            gives=form.gives.value,
        )


class Block(BaseModel):
    """A block a value or a column may use: the `name` a node gives as `block`, what it
    gives in words, and its forms. A block with more than one form, such as
    `min`, means the one its node's inputs fit.
    """

    name: str
    words: str
    forms: list[BlockForm]

    @classmethod
    def of(cls, block: blocks.Block) -> Self:
        return cls(
            name=block.name,
            words=block.words,
            forms=[BlockForm.of(form) for form in block.forms],
        )


class Catalogue(BaseModel):
    """Everything a value's or a column's tree may be made of. `blocks` in
    the catalogue's order. `leaves` the keys a task's value writes a leaf
    with, each alone in its mapping: `{runs: <group>}` a group's runs, for
    a fold's `over`; `{run: [<group>, <column>]}` that column of each run,
    inside a fold over that group; `{value: <name>}` another of the task's
    values; and `{fact: <name>}` one of `facts`, a fact of the submission.
    `board_leaves` those a leaderboard's column writes: `{results: <task>}`
    a task's results; `{value: [<task, pick column or block>, <value or
    fact>]}` a value or fact of a submission, the task's own read only
    inside `where`, `by` or a fold's `of`; `{column: <name>}` or `{column:
    [<board>, <name>]}` another column; and `best_each`'s `{name: <value>}`.
    `board_facts` the facts a column may read of a submission. A number is
    a leaf too. `skip` is what a block's `missing` says to leave out a run
    whose report is missing, or a submission whose input is missing,
    which otherwise makes a pick, fold or `best_each` missing; a number
    there counts as that number.
    `languages` are those an `exec` block's program may be written in.
    """

    blocks: list[Block]
    leaves: list[str]
    facts: list[str]
    board_leaves: list[str]
    board_facts: list[str]
    skip: str
    languages: list[str]
