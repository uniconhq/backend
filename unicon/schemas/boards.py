"""What the board, hold and marks routes answer with. A board comes back as
the caller reads it: its key and title, who it is for, its listed columns'
headers, the columns it was sorted by for them and those dropped, when the
hold holds other rows from, and its rows in order, each with its place,
its listed cells and how many of its submissions the hold keeps back,
every number an exact decimal string. A cell says whether it is hidden
and, on the caller's own row and for staff, names the submissions it
counted and those it left out as still waiting, each by task and number.
"""

import uuid
from datetime import datetime
from typing import Any, Literal

from forge.api import boards
from pydantic import BaseModel, Field

from unicon.schemas.exact import Exact


class BoardAudience(BaseModel):
    """Who a board is for: `staff`, `entrants` or `everyone`, and which
    `rows` they are given: `all`, `own`, or a number of top rows."""

    who: Literal["staff", "entrants", "everyone"]
    rows: Literal["all", "own"] | int


class SelfReported(BaseModel):
    """A value a column reads that reads a column the entrant could set."""

    task: str
    value: str


class Header(BaseModel):
    """One displayed column, the same for every row: its `name`, the decimal
    `places` it is shown to, null when the board gives none, the least and
    most it can give, both null unless both are known, and each
    self-reported value it reads, which a page marks on the column's
    header.
    """

    name: str
    places: int | None
    at_least: Exact | None
    at_most: Exact | None
    self_reported: list[SelfReported]


class Counted(BaseModel):
    """A submission a cell counted or left out, by its task and number."""

    task: str
    number: int


class BoardCell(BaseModel):
    """One listed column of a row: its `number`, null when missing or
    hidden; whether it is `hidden` from the caller, having read something
    they are not shown; the submissions it counted; and those it left out
    as still waiting, both null unless the row is the caller's own or they
    are staff."""

    column: str
    number: Exact | None
    hidden: bool
    counted: list[Counted] | None
    waiting: list[Counted] | None


class BoardRowOwner(BaseModel):
    """Whose a row is: an entrant by its id, and the name it is shown under,
    its own or its member's username, empty when the forge gives none.
    """

    entrant: uuid.UUID
    name: str


class BoardRow(BaseModel):
    """A row on the board: its place, shared by rows equal on every sort
    key, null on a board with no `sort`, when a sort key was dropped for
    the caller, and on a board showing them only their own row; whose it
    is; its listed cells in order; and `held`, how many of its submissions
    the hold keeps from the caller.
    """

    place: int | None
    row: BoardRowOwner
    cells: list[BoardCell]
    held: int


class SortKey(BaseModel):
    """A column rows are sorted by, in turn: `desc` puts the highest first,
    `asc` the lowest, and a row with no number comes after every row with
    one."""

    column: str
    way: Literal["desc", "asc"]


class Board(BaseModel):
    """One board as the caller reads it: the headers of the columns listed
    to them, the keys its rows were sorted by and the sort keys `dropped`,
    hidden on a row served or not listed, its rows cut to its audience, and
    `held_from`, when the hold holds other rows from, null when it holds
    nothing for the caller."""

    key: str
    title: str
    audience: BoardAudience
    headers: list[Header]
    sort: list[SortKey]
    dropped: list[str]
    held_from: datetime | None
    rows: list[BoardRow]


def header_of(header: boards.Header) -> dict[str, Any]:
    return {
        "name": header.name,
        "places": header.places,
        "at_least": header.at_least,
        "at_most": header.at_most,
        "self_reported": [{"task": task, "value": value} for task, value in header.self_reported],
    }


def sort_of(sort: tuple[tuple[str, str], ...]) -> list[dict[str, str]]:
    return [{"column": column, "way": way} for column, way in sort]


def counted_of(found: tuple[boards.Counted, ...]) -> list[dict[str, Any]]:
    return [{"task": each.task, "number": each.number} for each in found]


def board_of(board: boards.Board) -> dict[str, Any]:
    """A board as the forge works it out, as the API writes it."""
    return {
        "key": board.key,
        "title": board.title,
        "audience": {"who": board.audience.who, "rows": board.audience.rows},
        "headers": [header_of(header) for header in board.headers],
        "sort": sort_of(board.sort),
        "dropped": list(board.dropped),
        "held_from": board.held_from,
        "rows": [
            {
                "place": row.place,
                "row": {"entrant": row.owner.entrant_id, "name": row.name},
                "cells": [
                    {
                        "column": cell.column,
                        "number": cell.number,
                        "hidden": cell.hidden,
                        "counted": counted_of(cell.counted) if row.told else None,
                        "waiting": counted_of(cell.waiting) if row.told else None,
                    }
                    for cell in row.cells
                ],
                "held": row.held,
            }
            for row in board.rows
        ],
    }


class HoldRequest(BaseModel):
    """Ending the contest's hold early. Without `confirm` nothing changes,
    and the answer is `confirmation_required` with the words to show."""

    confirm: bool = False


class HoldState(BaseModel):
    """Where the contest's hold stands: its `from` and `until`, a time or
    `staff`, both null with no hold; whether it holds now; and, once staff
    ended it early, who, by user id and username, null when the forge gives
    none, and when."""

    from_: datetime | None = Field(serialization_alias="from")
    until: datetime | Literal["staff"] | None
    holding: bool
    ended_by: int | None
    ended_by_name: str | None
    ended_at: datetime | None


class Marks(BaseModel):
    """The marks the caller's row holds on a task, for a board reading which
    of its submissions an entrant marks: the numbers of the submissions
    marked, the most it may hold, and the row's close on the task, after
    which they are frozen.
    """

    numbers: list[int]
    most: int
    closes_at: datetime
    frozen: bool
