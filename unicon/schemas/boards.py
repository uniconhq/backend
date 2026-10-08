"""What the board and marks routes answer with. A board comes back as its
audience sees it now: its name, which groups it counts (`over`) and which
submission (`select`), the keys rows are ranked on, the tasks it covers,
what of them is not in its numbers yet, and its rows in rank order, every
number an exact decimal string. Only the reader's own row carries how many
of its submissions are still grading and which it counts; organisers get
both on every row. A board whose scope shows nothing yet comes back with no
rows and the time it is shown from.
"""

import dataclasses
import uuid
from datetime import datetime
from typing import Any

from forge.api.boards import Better, Over, Select, Who
from pydantic import BaseModel, model_validator

from unicon.schemas.exact import Exact


def _fields(given: Any) -> Any:
    if dataclasses.is_dataclass(given) and not isinstance(given, type):
        return dataclasses.asdict(given)
    return given


class BoardKey(BaseModel):
    """One key rows are ranked on, in turn: what it ranks by, `points`,
    `penalty` or a declared value, which way is better, null for a value no
    covered task gives a direction, and, on `penalty`, the minutes each
    attempt before the counted submission charges; a `per_attempt` of 0
    charges nothing, so the minute submitted is all it ranks on.
    """

    by: str
    better: Better | None
    per_attempt: int | None


class BoardTask(BaseModel):
    """A task the board covers: its name as `id`, its `label`, the letter of
    its place in the contest, and its `worth`, null on a task that gives no
    points.
    """

    id: str
    label: str
    worth: Exact | None

    @model_validator(mode="before")
    @classmethod
    def _from_column(cls, given: Any) -> Any:
        found = _fields(given)
        if isinstance(found, dict) and "name" in found:
            return {"id": found["name"], "label": found["label"], "worth": found["worth"]}
        return found


class NotInView(BaseModel):
    """What of a task is in the board's scope and not in its numbers yet:
    the groups whose verdict is not shown, and, on a board ranking a value,
    the `verdict` groups whose tests are not shown, with when they join.
    """

    task: str
    groups: list[str]
    tests_of: list[str]
    shown_at: datetime


class BoardCell(BaseModel):
    """A row's cell on a task: whether it counts, its number on each key it
    has one for, by the key's `by`, while it counts, and its attempts.
    `grading`, how many of the row's submissions are not graded yet, and
    `submissions`, the numbers of those it counts, several under
    `best_per_group`, come only in the reader's own row, and are null in
    every other.
    """

    counting: bool
    numbers: dict[str, Exact]
    attempts: int
    grading: int | None
    submissions: list[int] | None


class BoardRowOwner(BaseModel):
    """Whose a row is: a contestant by `user_id`, or a team by its id as
    `team`, and its name, a team's own or a contestant's username, empty
    when the forge gives none.
    """

    user_id: int | None
    team: uuid.UUID | None
    name: str


class BoardRow(BaseModel):
    """A row on the board: its rank, shared by rows tied on every key, whose
    it is, its number on each of the board's keys in turn, null where it
    has none, and its cell on each task by the task's name.
    """

    rank: int
    row: BoardRowOwner
    keys: list[Exact | None]
    cells: dict[str, BoardCell]

    @model_validator(mode="before")
    @classmethod
    def _from_ranked(cls, given: Any) -> Any:
        found = _fields(given)
        if not isinstance(found, dict) or "owner" not in found:
            return found
        owner = _fields(found["owner"])
        return {
            "rank": found["rank"],
            "row": {
                "user_id": owner.get("user_id"),
                "team": owner.get("team_id"),
                "name": found["name"],
            },
            "keys": found["keys"],
            "cells": found["cells"],
        }


class Board(BaseModel):
    """One board as the reader sees it now. `nothing_shown` is true, with no
    rows, while its scope shows nothing yet; `shown_at` is then the time its
    first group is shown, null while no task it covers is released.
    """

    board: str
    over: Over
    select: Select
    who: Who
    keys: list[BoardKey]
    tasks: list[BoardTask]
    not_in_view: list[NotInView]
    rows: list[BoardRow]
    nothing_shown: bool
    shown_at: datetime | None

    @model_validator(mode="before")
    @classmethod
    def _from_standings(cls, given: Any) -> Any:
        found = _fields(given)
        if not isinstance(found, dict) or not hasattr(found.get("board"), "name"):
            return found
        board = found["board"]
        return {
            "board": board.name,
            "over": board.over,
            "select": board.select,
            "who": board.who,
            "keys": found["keys"],
            "tasks": found["tasks"],
            "not_in_view": found["not_in_view"],
            "rows": found["rows"],
            "nothing_shown": found["nothing_shown"],
            "shown_at": found["shown_at"] if found["nothing_shown"] else None,
        }


class OrganisedBoard(BaseModel):
    """A board as organisers read it: `now`, every row given, or as the row
    picked sees it; `final`, every group of its scope counted as after the
    reveal; and what it asks of the tasks it covers that does not hold, each
    a sentence, which the save reported when the tasks were published.
    """

    now: Board
    final: Board
    notes: list[str]


class Marks(BaseModel):
    """The marks the caller's row holds on a task for its `marked` boards:
    the numbers of the submissions marked, the most it may hold, and the
    row's close on the task, after which they are frozen.
    """

    numbers: list[int]
    most: int
    closes_at: datetime
    frozen: bool
