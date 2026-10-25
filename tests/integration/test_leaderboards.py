"""The leaderboard, hold and marks routes: each caller reads a leaderboard as its
audience lets them, staff every leaderboard, row and cell, an entrant and a
visitor with no cookie a leaderboard for everyone, told what a cell counted only
on their own row, its numbers exact decimal strings; a manager of the
contest ends its hold early, asked first, and an observer reads where it
stands; the contest home carries an entrant's own row of each leaderboard; and a
row's marks on a task, up to the task's `marks`, refused on another's
submission and frozen at the row's close, only while a leaderboard reads which
submissions it marks.
"""

import re
from datetime import timedelta
from typing import Any

import httpx
from forge.testing import FakeClock, FakeForge

from tests.integration.conftest import (
    CONTEST,
    ORIGIN,
    TASK,
    entrant_of,
    read,
    run_pipelines,
    sign_in_as,
    upload,
)

PUBLIC = "/api/v1/public/contests/acme/spring/leaderboards"
LEADERBOARDS = f"{CONTEST}/leaderboards"
ORGANISED = f"{TASK}/organise/submissions/1"
MARKS = f"{TASK}/marks"
SETTINGS = """\
leaderboards:
  standings:
    title: Standings
    audience: {who: everyone}
    columns:
      picked: {block: latest, from: {results: sum}}
      score: {block: otherwise, of: [{value: [{column: picked}, score]}, 0]}
    sort: [{score: desc}]
    display: [{score: {places: 1}}]
  private:
    columns:
      tries: {block: count, over: {results: sum}}
    display: [tries]
"""
HOLD = "hold: {from: 2026-09-26T12:30:00Z, until: staff}\n"
"""A hold from half an hour after the tests' clock starts, inside the contest."""
MARKED = """\
leaderboards:
  final:
    columns:
      score: {value: [{block: latest, from: {results: sum}, where: {value: [sum, marked]}}, score]}
"""


async def _settings(
    client: httpx.AsyncClient, forge: FakeForge, leaderboards: str, marks: int = 0
) -> None:
    """acme/spring's settings with `leaderboards` and, given `marks`, that many
    marks on sum, written by ada, leaving carol signed in.
    """
    await sign_in_as(client, forge, 7)
    settings = await read(client, f"{CONTEST}/files/contest.yaml")
    content = re.sub(r"(?ms)^leaderboards:.*?(?=^\S|\Z)", "", settings["content"])
    content = content.rstrip("\n") + "\n" + leaderboards
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
    """A submission by the signed-in contestant, its pipeline run with its
    one run ending `outcome`.
    """
    made = await upload(client, forge, f"print({key!r})\n".encode())
    submitted = await client.post(
        f"{TASK}/submissions",
        json={
            "idempotency_key": key,
            "inputs": {
                "code": {"uploads": [made["id"]]},
                "language": {"value": "python"},
            },
        },
        headers=ORIGIN,
    )
    assert submitted.status_code == 201, submitted.text
    await run_pipelines(client, verdict=outcome)


def _standings(carols: str, told: bool) -> dict[str, Any]:
    """The leaderboard for everyone with carol's row alone, her one
    submission accepted, as staff, carol and a visitor read it."""
    counted: list[Any] | None = [{"task": "sum", "number": 1}] if told else None
    waiting: list[Any] | None = [] if told else None
    return {
        "key": "standings",
        "title": "Standings",
        "audience": {"who": "everyone", "rows": "all"},
        "headers": [
            {
                "name": "score",
                "places": 1,
                "at_least": "0",
                "at_most": "1",
                "self_reported": [],
            }
        ],
        "sort": [{"column": "score", "way": "desc"}],
        "dropped": [],
        "held_from": None,
        "rows": [
            {
                "place": 1,
                "row": {"entrant": carols, "name": "carol"},
                "cells": [
                    {
                        "column": "score",
                        "number": "1",
                        "text": None,
                        "hidden": False,
                        "counted": counted,
                        "waiting": waiting,
                    }
                ],
                "held": 0,
                "grading": 0 if told else None,
            }
        ],
    }


async def test_each_caller_reads_the_leaderboards_its_audience_lets_them(
    client: httpx.AsyncClient, entered: FakeForge
) -> None:
    carols = await entrant_of(client)
    await _settings(client, entered, SETTINGS)
    await _graded(client, entered, "key-0001-aaaa")

    mine = await client.get(LEADERBOARDS)
    one = await client.get(f"{LEADERBOARDS}/standings")
    not_hers = await client.get(f"{LEADERBOARDS}/private")
    client.cookies.clear()
    public = await client.get(PUBLIC)
    public_one = await client.get(f"{PUBLIC}/standings")
    public_private = await client.get(f"{PUBLIC}/private")
    await sign_in_as(client, entered, 7)
    staff = await client.get(LEADERBOARDS)
    staff_one = await client.get(f"{LEADERBOARDS}/standings")
    other = await client.get(f"{LEADERBOARDS}/nothing")
    organise = await client.get(f"{CONTEST}/organise/leaderboards")

    # Carol's one submission passed its one run, so the row's score is 1.
    # Carol is told what her own row's cells counted; a visitor is not.
    assert (mine.status_code, mine.json()) == (200, [_standings(carols, told=True)])
    assert one.json() == _standings(carols, told=True)
    assert (public.status_code, public.json()) == (200, [_standings(carols, told=False)])
    assert public_one.json() == _standings(carols, told=False)
    # The leaderboard with no audience is staff's alone.
    for refused in (not_hers, public_private):
        assert (refused.status_code, refused.json()["code"]) == (404, "not_found")
    assert staff.status_code == 200, staff.text
    standings, private = staff.json()
    assert standings == staff_one.json() == _standings(carols, told=True)
    assert private["rows"][0]["cells"] == [
        {
            "column": "tries",
            "number": "1",
            "text": None,
            "hidden": False,
            "counted": [{"task": "sum", "number": 1}],
            "waiting": [],
        }
    ]
    assert (other.status_code, other.json()["code"]) == (404, "not_found")
    assert organise.status_code == 404


async def test_a_manager_of_the_contest_ends_its_hold_early_asked_first(
    client: httpx.AsyncClient, entered: FakeForge, clock: FakeClock
) -> None:
    await _settings(client, entered, HOLD + SETTINGS)
    clock.advance(timedelta(hours=1))
    await _graded(client, entered, "key-0001-aaaa")
    client.cookies.clear()
    held = (await client.get(f"{PUBLIC}/standings")).json()
    await sign_in_as(client, entered, 7)

    before = await client.get(f"{CONTEST}/hold")
    asked = await client.post(f"{CONTEST}/hold/end", json={}, headers=ORIGIN)
    ended = await client.post(f"{CONTEST}/hold/end", json={"confirm": True}, headers=ORIGIN)
    again = await client.post(f"{CONTEST}/hold/end", json={"confirm": True}, headers=ORIGIN)
    client.cookies.clear()
    after = (await client.get(f"{PUBLIC}/standings")).json()

    # A visitor reads every row as it stood at the hold's from until the
    # hold ends: carol's submission came after it, so it is held until then.
    assert held["held_from"] == "2026-09-26T12:30:00Z"
    assert before.json() == {
        "from": "2026-09-26T12:30:00Z",
        "until": "staff",
        "holding": True,
        "ended_by": None,
        "ended_by_name": None,
        "ended_at": None,
    }
    assert (asked.status_code, asked.json()["code"]) == (409, "confirmation_required")
    assert asked.json()["action"] == "end_hold"
    assert ended.status_code == 200, ended.text
    assert {key: ended.json()[key] for key in ("holding", "ended_by", "ended_by_name")} == {
        "holding": False,
        "ended_by": 7,
        "ended_by_name": "ada",
    }
    assert again.json() == ended.json()
    assert after["held_from"] is None
    [held_row] = held["rows"]
    [after_row] = after["rows"]
    assert (held_row["cells"][0]["number"], held_row["held"]) == ("0", 1)
    assert (after_row["cells"][0]["number"], after_row["held"]) == ("1", 0)


async def test_the_contest_home_carries_the_entrants_own_row_of_each_leaderboard(
    client: httpx.AsyncClient, entered: FakeForge
) -> None:
    carols = await entrant_of(client)
    await _settings(client, entered, SETTINGS)
    await _graded(client, entered, "key-0001-aaaa")

    home = (await client.get(f"{CONTEST}/home")).json()

    assert home["standing"] == [_standings(carols, told=True)]


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


async def test_a_task_no_leaderboard_reads_the_marks_of_takes_no_marks(
    client: httpx.AsyncClient, entered: FakeForge
) -> None:
    await _settings(client, entered, SETTINGS)

    page = await client.get(f"{TASK}/page")
    refused = await client.get(MARKS)

    assert page.json()["marks"] is None
    assert (refused.status_code, refused.json()["code"]) == (409, "marks_off")


async def test_the_leaderboard_routes_need_a_session_but_the_public_ones(
    client: httpx.AsyncClient, entered: FakeForge
) -> None:
    client.cookies.clear()

    answers = [
        await client.get(LEADERBOARDS),
        await client.get(MARKS),
        await client.put(f"{MARKS}/1", headers=ORIGIN),
    ]

    assert [(answer.status_code, answer.json()["code"]) for answer in answers] == [
        (401, "unauthenticated")
    ] * 3


async def test_a_save_of_the_contests_settings_refuses_a_leaderboard_at_its_path(
    client: httpx.AsyncClient, entered: FakeForge
) -> None:
    await sign_in_as(client, entered, 7)
    settings = await read(client, f"{CONTEST}/files/contest.yaml")
    content = re.sub(r"(?ms)^leaderboards:.*?(?=^\S|\Z)", "", settings["content"])
    shown_pick = SETTINGS.replace("display: [{score", "display: [picked, {score")

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
    carols = await entrant_of(client)
    await _graded(client, entered, "key-0001-aaaa")
    own = (await client.get(f"{TASK}/submissions/1")).json()["grading"]
    refused = await client.get(ORGANISED, params={"entrant": carols})
    await sign_in_as(client, entered, 7)

    seen = await client.get(ORGANISED, params={"entrant": carols})

    assert (refused.status_code, refused.json()["code"]) == (403, "forbidden")
    assert seen.status_code == 200, seen.text
    grading = seen.json()["grading"]
    # Carol is shown her run with no id and an empty tuple, since the task's
    # `show` lists neither test file, and not the compile log; organisers
    # read every one of them, each value with when it shows and what it read.
    [mine] = own["runs"]
    [run] = grading["runs"]
    assert (own["status"], mine["id"], mine["tuples"], own["once"]["texts"]) == (
        "graded",
        None,
        [{"title": None, "key": {}}],
        {},
    )
    assert (grading["status"], run["id"], run["verdict"]) == ("done", "r1", "accepted")
    assert run["tuples"] == [
        {"title": None, "key": {"input": "tests/1.in", "answer": "tests/1.ans"}}
    ]
    by_title = {report["title"]: report for report in run["reports"]}
    assert by_title["Run time"] == {"title": "Run time", "unit": "ms", "number": "12"}
    assert list(grading["once"]["texts"]) == ["log"]
    [score] = grading["run_values"]
    assert (score["number"], score["show"], score["runs"]) == ("1", "now", ["r1"])
    assert grading["facts"] == {"seconds_late": "0", "seconds": "7200", "compiled": "1"}


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
