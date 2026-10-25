"""The board and marks routes: until audiences come, staff alone read a
board, every row and cell, its numbers exact decimal strings, and an
entrant and a visitor with no cookie read none; and a row's marks on a
task, up to the task's `marks`, refused on another's submission and frozen
at the row's close, only while a board reads which submissions it marks.
"""

import re
from datetime import timedelta
from typing import Any
from urllib.parse import urlsplit

import httpx
from forge.testing import FakeClock, FakeForge

from tests.integration.conftest import (
    CONTEST,
    ORIGIN,
    TASK,
    edit_task,
    entrant_of,
    read,
    sign_in_as,
    upload,
)

PUBLIC = "/api/v1/public/contests/acme/spring/boards"
BOARDS = f"{CONTEST}/boards"
ORGANISED = f"{TASK}/organise/submissions/1"
MARKS = f"{TASK}/marks"
SETTINGS = """\
leaderboards:
  standings:
    title: Standings
    audience: {who: everyone}
    columns:
      picked: {block: latest, from: {results: sum}}
      score: {block: otherwise, of: [{value: [{column: picked}, total]}, 0]}
    sort: [{score: desc}]
    display: [{score: {places: 1}}]
"""
MARKED = """\
leaderboards:
  final:
    columns:
      score: {value: [{block: latest, from: {results: sum}, where: {value: [sum, marked]}}, total]}
"""


async def _settings(
    client: httpx.AsyncClient, forge: FakeForge, boards: str, marks: int = 0
) -> None:
    """acme/spring's settings with `boards` and, given `marks`, that many
    marks on sum, written by ada, leaving carol signed in.
    """
    await sign_in_as(client, forge, 7)
    settings = await read(client, f"{CONTEST}/files/contest.yaml")
    content = re.sub(r"(?ms)^leaderboards:.*?(?=^\S|\Z)", "", settings["content"])
    content = content.rstrip("\n") + "\n" + boards
    if marks:
        content = re.sub(r"(?m)^(\s*- id: sum)$", rf"\1\n    marks: {marks}", content)
    written = await client.put(
        f"{CONTEST}/files/contest.yaml",
        json={"encoding": "utf-8", "content": content, "token": settings["token"]},
        headers=ORIGIN,
    )
    assert written.status_code == 200, written.text
    await sign_in_as(client, forge, 20)


async def _graded(
    client: httpx.AsyncClient, forge: FakeForge, key: str, outcome: str = "accepted"
) -> None:
    """A submission by the signed-in contestant, its run finished with one
    test of `outcome`.
    """
    made = await upload(client, forge, f"print({key!r})\n".encode())
    submitted = await client.post(
        f"{TASK}/submissions",
        json={
            "idempotency_key": key,
            "inputs": {
                "submission": {"uploads": [made["id"]]},
                "language": {"value": "python"},
            },
        },
        headers=ORIGIN,
    )
    assert submitted.status_code == 201, submitted.text
    grading = submitted.json()["grading"]["id"]
    [run] = [run for run in forge.ci.runs.values() if run.variables["UNICON_GRADING_ID"] == grading]
    address = urlsplit(run.variables["UNICON_ENVELOPE_URL"])
    envelope = (await client.get(f"{address.path}?{address.query}")).json()
    result: dict[str, Any] = {
        "schema_version": 5,
        "stopped": None,
        "stopped_by": None,
        "tests": [{"test": "main/1", "outcome": outcome, "values": {"time_ms": 12.5}}],
        "values": {},
        "run_log": None,
        "error": None,
    }
    finished = await client.post(
        urlsplit(envelope["callback"]["url"]).path,
        json={"event": "finished", "result": result},
        headers={"Authorization": f"Bearer {envelope['callback']['token']}"},
    )
    assert finished.json() == {"status": "done"}, finished.text


async def test_staff_read_every_row_of_a_board_and_nobody_else_reads_one(
    client: httpx.AsyncClient, entered: FakeForge
) -> None:
    carols = await entrant_of(client)
    await _settings(client, entered, SETTINGS)
    await _graded(client, entered, "key-0001-aaaa")

    mine = await client.get(BOARDS)
    one = await client.get(f"{BOARDS}/standings")
    client.cookies.clear()
    public = await client.get(PUBLIC)
    public_one = await client.get(f"{PUBLIC}/standings")
    await sign_in_as(client, entered, 7)
    staff = await client.get(BOARDS)
    staff_one = await client.get(f"{BOARDS}/standings")
    other = await client.get(f"{BOARDS}/nothing")
    organise = await client.get(f"{CONTEST}/organise/boards")

    assert (mine.status_code, mine.json()) == (200, [])
    assert (one.status_code, one.json()["code"]) == (404, "not_found")
    assert (public.status_code, public.json()) == (200, [])
    assert (public_one.status_code, public_one.json()["code"]) == (404, "not_found")
    assert staff.status_code == 200, staff.text
    # sum is graded test by test, which a board does not read, so the
    # row's score is otherwise's 0.
    standings = {
        "key": "standings",
        "title": "Standings",
        "audience": {"who": "everyone", "rows": "all"},
        "headers": [
            {
                "name": "score",
                "places": 1,
                "at_least": None,
                "at_most": None,
                "self_reported": [],
            }
        ],
        "sort": [{"column": "score", "way": "desc"}],
        "rows": [
            {
                "place": 1,
                "row": {"entrant": carols, "name": "carol"},
                "cells": [{"column": "score", "number": "0", "counted": [], "waiting": []}],
            }
        ],
    }
    assert staff.json() == [standings]
    assert staff_one.json() == standings
    assert (other.status_code, other.json()["code"]) == (404, "not_found")
    assert organise.status_code == 404


async def test_a_row_marks_its_own_submissions_up_to_the_tasks_marks_until_its_close(
    client: httpx.AsyncClient, entered: FakeForge, clock: FakeClock
) -> None:
    await _settings(client, entered, MARKED, marks=1)
    await _graded(client, entered, "key-0001-aaaa")
    clock.advance(timedelta(minutes=1))
    await _graded(client, entered, "key-0002-bbbb", outcome="wrong_answer")

    page = await client.get(f"{TASK}/page")
    held = await client.get(MARKS)
    marked = await client.put(f"{MARKS}/1", headers=ORIGIN)
    again = await client.put(f"{MARKS}/1", headers=ORIGIN)
    over = await client.put(f"{MARKS}/2", headers=ORIGIN)
    missing = await client.put(f"{MARKS}/3", headers=ORIGIN)
    unmarked = await client.delete(f"{MARKS}/1", headers=ORIGIN)
    await client.put(f"{MARKS}/2", headers=ORIGIN)
    clock.advance(timedelta(hours=3))
    frozen = await client.put(f"{MARKS}/1", headers=ORIGIN)

    closes = "2026-09-26T15:00:00Z"
    assert page.json()["marks"] == 1
    assert held.json() == {"numbers": [], "most": 1, "closes_at": closes, "frozen": False}
    assert marked.json() == again.json() == {**held.json(), "numbers": [1]}
    assert (over.status_code, over.json()["code"], over.json()["limit"]) == (409, "mark_limit", 1)
    assert (missing.status_code, missing.json()["code"]) == (404, "not_found")
    assert unmarked.json() == held.json()
    assert (frozen.status_code, frozen.json()["code"]) == (403, "marks_frozen")
    assert (await client.get(MARKS)).json() == {
        "numbers": [2],
        "most": 1,
        "closes_at": closes,
        "frozen": True,
    }


async def test_a_task_no_board_reads_the_marks_of_takes_no_marks(
    client: httpx.AsyncClient, entered: FakeForge
) -> None:
    await _settings(client, entered, SETTINGS)

    page = await client.get(f"{TASK}/page")
    refused = await client.get(MARKS)

    assert page.json()["marks"] is None
    assert (refused.status_code, refused.json()["code"]) == (409, "marks_off")


async def test_the_board_routes_need_a_session_but_the_public_ones(
    client: httpx.AsyncClient, entered: FakeForge
) -> None:
    client.cookies.clear()

    answers = [
        await client.get(BOARDS),
        await client.get(MARKS),
        await client.put(f"{MARKS}/1", headers=ORIGIN),
    ]

    assert [(answer.status_code, answer.json()["code"]) for answer in answers] == [
        (401, "unauthenticated")
    ] * 3


async def test_a_save_of_the_contests_settings_refuses_a_board_at_its_path(
    client: httpx.AsyncClient, entered: FakeForge
) -> None:
    await sign_in_as(client, entered, 7)
    settings = await read(client, f"{CONTEST}/files/contest.yaml")
    content = re.sub(r"(?ms)^leaderboards:.*?(?=^\S|\Z)", "", settings["content"])
    shown_pick = SETTINGS.replace("display: [", "display: [picked, ")

    refused = await client.put(
        f"{CONTEST}/files/contest.yaml",
        json={"content": content.rstrip("\n") + "\n" + shown_pick, "token": settings["token"]},
        headers=ORIGIN,
    )

    assert (refused.status_code, refused.json()["code"]) == (422, "invalid_definition")
    assert [error["path"] for error in refused.json()["errors"]] == [
        "leaderboards.standings.display[0]"
    ]


async def test_a_save_of_the_contests_settings_with_nothing_to_report_answers_no_notes(
    client: httpx.AsyncClient, entered: FakeForge
) -> None:
    await sign_in_as(client, entered, 7)
    settings = await read(client, f"{CONTEST}/files/contest.yaml")
    content = re.sub(r"(?ms)^leaderboards:.*?(?=^\S|\Z)", "", settings["content"])

    written = await client.put(
        f"{CONTEST}/files/contest.yaml",
        json={"content": content.rstrip("\n") + "\n" + SETTINGS, "token": settings["token"]},
        headers=ORIGIN,
    )

    assert written.status_code == 200, written.text
    assert written.json()["notes"] == []


async def test_organisers_read_a_submission_scored_with_everything_filled_in(
    client: httpx.AsyncClient, entered: FakeForge
) -> None:
    await sign_in_as(client, entered, 7)
    await edit_task(client, "main: {each: 100}", "main: {each: 100, show: after_close}")
    await sign_in_as(client, entered, 20)
    carols = await entrant_of(client)
    await _graded(client, entered, "key-0001-aaaa")
    own = (await client.get(f"{TASK}/submissions/1")).json()["grading"]
    refused = await client.get(ORGANISED, params={"entrant": carols})
    await sign_in_as(client, entered, 7)

    seen = await client.get(ORGANISED, params={"entrant": carols})

    assert (refused.status_code, refused.json()["code"]) == (403, "forbidden")
    assert seen.status_code == 200, seen.text
    grading = seen.json()["grading"]
    [main] = grading["groups"]
    [mine] = own["groups"]
    assert (main["outcome"], main["points"], main["max"]) == ("accepted", "100", "100")
    assert [test["test"] for test in main["tests"]] == ["main/1"]
    assert main["shown_at"] == mine["shown_at"] == "2026-09-26T15:00:00Z"
    assert (grading["status"], grading["outcome"]) == ("done", "accepted")
    assert grading["points"] == {"shown": "100", "pending": "0", "pending_until": None}
    assert (mine["outcome"], mine["tests"], mine["points"]) == (None, None, None)
    assert (own["status"], own["points"]["pending"]) == ("graded", "100")


async def test_the_contest_home_leaves_a_tasks_standing_to_the_boards(
    client: httpx.AsyncClient, entered: FakeForge
) -> None:
    await _settings(client, entered, SETTINGS)
    await _graded(client, entered, "key-0001-aaaa")

    home = (await client.get(f"{CONTEST}/home")).json()

    assert "boards" not in home
    assert ["points" in task for task in home["tasks"]] == [False]


async def test_organisers_pick_one_row_with_such_a_submission(
    client: httpx.AsyncClient, entered: FakeForge
) -> None:
    carols = await entrant_of(client)
    await _graded(client, entered, "key-0001-aaaa")
    await sign_in_as(client, entered, 7)
    nobody = "0192f4a4-7b7e-7000-8000-000000000001"

    answers = [
        await client.get(ORGANISED),
        await client.get(ORGANISED, params={"entrant": "carol"}),
        await client.get(ORGANISED, params={"entrant": nobody}),
        await client.get(f"{TASK}/organise/submissions/2", params={"entrant": carols}),
    ]

    assert [(answer.status_code, answer.json()["code"]) for answer in answers] == [
        (422, "validation_error"),
        (422, "validation_error"),
        (404, "not_found"),
        (404, "not_found"),
    ]
