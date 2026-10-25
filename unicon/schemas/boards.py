"""What the board and marks routes answer with. A board comes back as staff
read it until audiences come: its key and title, who it is for, its
displayed columns' headers, the columns it sorts by, and its rows in
order, each with its place and its displayed cells, every number an exact
decimal string. A cell names the submissions it counted and those it left
out as still waiting, each by task and number.
"""

import uuid
from datetime import datetime
from typing import Any, Literal

from forge.api import boards
from pydantic import BaseModel

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
    """One displayed column of a row: its `number`, null when missing; the
    submissions it counted; and those it left out as still waiting."""

    column: str
    number: Exact | None
    counted: list[Counted]
    waiting: list[Counted]


class BoardRowOwner(BaseModel):
    """Whose a row is: an entrant by its id, and the name it is shown under,
    its own or its member's username, empty when the forge gives none.
    """

    entrant: uuid.UUID
    name: str


class BoardRow(BaseModel):
    """A row on the board: its place, shared by rows equal on every sort
    key, null on a board with no `sort`, whose it is, and its displayed
    cells in order.
    """

    place: int | None
    row: BoardRowOwner
    cells: list[BoardCell]


class SortKey(BaseModel):
    """A column rows are sorted by, in turn: `desc` puts the highest first,
    `asc` the lowest, and a row with no number comes after every row with
    one."""

    column: str
    way: Literal["desc", "asc"]


class Board(BaseModel):
    """One board as staff read it: every row, no hold."""

    key: str
    title: str
    audience: BoardAudience
    headers: list[Header]
    sort: list[SortKey]
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
        "rows": [
            {
                "place": row.place,
                "row": {"entrant": row.owner.entrant_id, "name": row.name},
                "cells": [
                    {
                        "column": cell.column,
                        "number": cell.number,
                        "counted": counted_of(cell.counted),
                        "waiting": counted_of(cell.waiting),
                    }
                    for cell in row.cells
                ],
            }
            for row in board.rows
        ],
    }


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
