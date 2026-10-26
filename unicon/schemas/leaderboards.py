"""What the leaderboard routes answer with. A leaderboard comes back as
the caller reads it: its key and title, who it is for, its listed columns'
headers, the columns it was sorted by for them and those dropped, when the
hold holds other rows from, and its rows in order, each with its place,
its listed cells and how many of its submissions the hold keeps back,
every number an exact decimal string. On the caller's own row and for
staff, a cell says whether it is hidden and names the submissions it
counted and those it left out as still waiting, each by task and number,
and the row says how many of its submissions still grade; on any other
row a cell with no number says no more, whether it is hidden, waiting or
missing.
"""

import uuid
from datetime import datetime
from typing import Any, Literal

from forge.api import leaderboards
from pydantic import BaseModel

from unicon.schemas.exact import Exact


class LeaderboardAudience(BaseModel):
    """Who a leaderboard is for: `staff`, `entrants` or `everyone`, and which
    `rows` they are given: `all`, `own`, or a number of top rows."""

    who: Literal["staff", "entrants", "everyone"]
    rows: Literal["all", "own"] | int


class SelfReported(BaseModel):
    """A value a column reads that reads a column the entrant could set."""

    task: str
    value: str


class Header(BaseModel):
    """One displayed column, the same for every row: its `name`, the
    `decimals` it is shown to, null when the leaderboard gives none, the least and
    most it can give, both null unless both are known, and each
    self-reported value it reads, which a page marks on the column's
    header.
    """

    name: str
    decimals: int | None
    at_least: Exact | None
    at_most: Exact | None
    self_reported: list[SelfReported]


class Counted(BaseModel):
    """A submission a cell counted or left out, by its task and number."""

    task: str
    number: int


class LeaderboardCell(BaseModel):
    """One listed column of a row: its `number`, null when missing, hidden,
    waiting or text; its `text`, null when it is a number or missing;
    whether it is `hidden` from the caller, having read
    something they are not shown, told only on the caller's own row and to
    staff and false elsewhere; the submissions it counted; and those it
    left out as still waiting, both null unless the row is the caller's
    own or they are staff."""

    column: str
    number: Exact | None
    text: str | None = None
    hidden: bool
    counted: list[Counted] | None
    waiting: list[Counted] | None


class LeaderboardRowOwner(BaseModel):
    """Whose a row is: an entrant by its id, and the name it is shown under,
    its own or its member's username, empty when the forge gives none.
    """

    entrant: uuid.UUID
    name: str


class LeaderboardRow(BaseModel):
    """A row on the leaderboard: its place, shared by rows equal on every sort
    key, null on a leaderboard with no `sort`, when a sort key was dropped for
    the caller, and on a leaderboard showing them only their own row; whose it
    is; its listed cells in order; `held`, how many of its submissions
    the hold keeps from the caller; and `grading`, how many of its
    submissions to the tasks the leaderboard reads still grade, a value the
    caller is shown still to come, null unless the row is the caller's
    own or they are staff.
    """

    place: int | None
    row: LeaderboardRowOwner
    cells: list[LeaderboardCell]
    held: int
    grading: int | None


class SortKey(BaseModel):
    """A column rows are sorted by, in turn: `desc` puts the highest first,
    `asc` the lowest, and a row with no number comes after every row with
    one."""

    column: str
    way: Literal["desc", "asc"]


class Leaderboard(BaseModel):
    """One leaderboard as the caller reads it: the headers of the columns listed
    to them, the keys its rows were sorted by and the sort keys `dropped`,
    hidden on a row served or not listed, its rows cut to its audience, and
    `held_from`, when the hold holds other rows from, null when it holds
    nothing for the caller."""

    key: str
    title: str
    audience: LeaderboardAudience
    headers: list[Header]
    sort: list[SortKey]
    dropped: list[str]
    held_from: datetime | None
    rows: list[LeaderboardRow]


def header_of(header: leaderboards.Header) -> dict[str, Any]:
    return {
        "name": header.name,
        "decimals": header.decimals,
        "at_least": header.at_least,
        "at_most": header.at_most,
        "self_reported": [{"task": task, "value": value} for task, value in header.self_reported],
    }


def sort_of(sort: tuple[tuple[str, str], ...]) -> list[dict[str, str]]:
    return [{"column": column, "way": way} for column, way in sort]


def counted_of(found: tuple[leaderboards.Counted, ...]) -> list[dict[str, Any]]:
    return [{"task": each.task, "number": each.number} for each in found]


def leaderboard_of(leaderboard: leaderboards.LeaderboardView) -> dict[str, Any]:
    """A leaderboard as the forge works it out, as the API writes it."""
    return {
        "key": leaderboard.key,
        "title": leaderboard.title,
        "audience": {"who": leaderboard.audience.who, "rows": leaderboard.audience.rows},
        "headers": [header_of(header) for header in leaderboard.headers],
        "sort": sort_of(leaderboard.sort),
        "dropped": list(leaderboard.dropped),
        "held_from": leaderboard.held_from,
        "rows": [
            {
                "place": row.place,
                "row": {"entrant": row.owner.entrant_id, "name": row.name},
                "cells": [
                    {
                        "column": cell.column,
                        "number": cell.number,
                        "text": cell.text,
                        "hidden": cell.hidden,
                        "counted": counted_of(cell.counted) if row.told else None,
                        "waiting": counted_of(cell.waiting) if row.told else None,
                    }
                    for cell in row.cells
                ],
                "held": row.held,
                "grading": row.grading if row.told else None,
            }
            for row in leaderboard.rows
        ],
    }
