"""The blocks a task's values are built from, as the editor reads them
(SIMPLER-CORE.md 14 and 19): each block once, what it gives in words, and
its forms, each with the inputs it takes and the kind each one takes; with
the leaves a tree may hold, the facts a value may read, the word a
fold's `missing` takes to leave a run out and the languages a program
may be written in.
"""

from typing import Literal, Self

from forge.api import blocks
from pydantic import BaseModel


class BlockInput(BaseModel):
    """One input of a form: the `kind` it takes, a number, a group's `runs`,
    `weights` by a repeated input's values, what a `missing` report counts
    as, a `path`, a folder of the task such as `programs/mean/`, or a
    `language`, one of the catalogue's `languages`; a list of at least
    `least` and at most `most` when `least` is given (`most` null for no
    most), one node otherwise; whether it may be left out; whether a fold
    reads it once for each run (`per_run`); and whether it takes a number
    written out alone, never a leaf or a block (`plain`).
    """

    kind: Literal["number", "runs", "weights", "missing", "path", "language"]
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
    such as "numbers" or "a group's runs", and its inputs by name, in the
    order a node writes them.
    """

    given: str
    inputs: dict[str, BlockInput]

    @classmethod
    def of(cls, form: blocks.Form) -> Self:
        return cls(
            given=form.given,
            inputs={name: BlockInput.of(given) for name, given in form.inputs.items()},
        )


class Block(BaseModel):
    """A block a value may use: the `name` a node gives as `block`, what it
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
    """Everything a value's tree may be made of. `blocks` in the
    catalogue's order. `leaves` the keys a leaf is written with, each alone
    in its mapping: `{runs: <group>}` a group's runs, for a fold's `over`;
    `{run: [<group>, <column>]}` that column of each run, inside a fold over
    that group; `{value: <name>}` another of the task's values; and
    `{fact: <name>}` one of `facts`, a fact of the submission. A number is a
    leaf too. `skip` is what a fold's `missing` says to leave out a run whose
    report is missing; a number there counts as that number. `languages`
    are those an `exec` block's program may be written in.
    """

    blocks: list[Block]
    leaves: list[str]
    facts: list[str]
    skip: str
    languages: list[str]
