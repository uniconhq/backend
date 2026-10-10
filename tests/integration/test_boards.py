"""The board and marks routes: a board served to each audience it names, a
visitor with no cookie among them, an ICPC board's penalty charging its
earlier attempt, its numbers exact decimal strings and
only the reader's own row carrying its grading count and counted
submissions; organisers every board `now` and `final`, with a row of the contest to read
the boards it sees `now` as, and nobody else; and a row's marks on a task, up to the task's
`marks`, refused on another's submission and frozen at the row's close.
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
    read,
    sign_in_as,
    upload,
)

PUBLIC = "/api/v1/public/contests/acme/spring/boards"
BOARDS = f"{CONTEST}/boards"
ORGANISE = f"{CONTEST}/organise/boards"
ORGANISED = f"{TASK}/organise/submissions/1"
MARKS = f"{TASK}/marks"
SETTINGS = """\
leaderboards:
  - {name: Standings, who: everyone, order: [points, {by: penalty, per_attempt: 20}]}
  - {name: Staff, order: [points]}
"""
MARKED = """\
leaderboards:
  - {name: Final, who: contestants, select: marked}
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


async def _ranked(client: httpx.AsyncClient, forge: FakeForge, clock: FakeClock) -> None:
    """The boards of `SETTINGS`, and carol wrong at 12:00 and right at 12:01:
    121 minutes and one attempt of 20 on the penalty.
    """
    await _settings(client, forge, SETTINGS)
    await _graded(client, forge, "key-0001-aaaa", outcome="wrong_answer")
    clock.advance(timedelta(minutes=1))
    await _graded(client, forge, "key-0002-bbbb")


def _standings(cell: dict[str, Any]) -> dict[str, Any]:
    return {
        "board": "Standings",
        "over": "all",
        "select": "best",
        "who": "everyone",
        "keys": [
            {"by": "points", "better": "higher", "per_attempt": None},
            {"by": "penalty", "better": "lower", "per_attempt": 20},
        ],
        "tasks": [{"id": "sum", "label": "A", "worth": "100"}],
        "not_in_view": [],
        "rows": [
            {
                "rank": 1,
                "row": {"user_id": 20, "team": None, "name": "carol"},
                "keys": ["100", "141"],
                "cells": {"sum": cell},
            }
        ],
        "nothing_shown": False,
        "shown_at": None,
    }


OWN_CELL = {
    "counting": True,
    "numbers": {"points": "100", "penalty": "141"},
    "attempts": 1,
    "grading": 0,
    "submissions": [2],
}
OTHER_CELL = {**OWN_CELL, "grading": None, "submissions": None}


async def test_a_board_is_served_to_each_audience_it_names(
    client: httpx.AsyncClient, entered: FakeForge, clock: FakeClock
) -> None:
    await _ranked(client, entered, clock)

    mine = await client.get(BOARDS)
    one = await client.get(f"{BOARDS}/Standings")
    staff = await client.get(f"{BOARDS}/Staff")
    client.cookies.clear()
    public = await client.get(PUBLIC)
    public_one = await client.get(f"{PUBLIC}/Standings")

    assert mine.status_code == 200, mine.text
    assert mine.json() == [_standings(OWN_CELL)]
    assert one.json() == _standings(OWN_CELL)
    assert (staff.status_code, staff.json()["code"]) == (404, "not_found")
    assert public.json() == [_standings(OTHER_CELL)]
    assert public_one.json() == _standings(OTHER_CELL)


async def test_organisers_read_every_board_now_and_final_and_nobody_else_does(
    client: httpx.AsyncClient, entered: FakeForge, clock: FakeClock
) -> None:
    await _ranked(client, entered, clock)
    refused = await client.get(ORGANISE)
    await sign_in_as(client, entered, 7)

    organised = await client.get(ORGANISE)
    as_carol = await client.get(ORGANISE, params={"user_id": 20})
    nobody = await client.get(ORGANISE, params={"user_id": 99})
    both = await client.get(
        ORGANISE, params={"user_id": 20, "team": "0192f4a4-7b7e-7000-8000-000000000001"}
    )

    assert (refused.status_code, refused.json()["code"]) == (403, "forbidden")
    assert organised.status_code == 200, organised.text
    standings, staff = organised.json()
    assert standings["now"] == standings["final"] == _standings(OWN_CELL)
    assert standings["notes"] == []
    assert (staff["now"]["board"], staff["now"]["who"]) == ("Staff", "organisers")
    assert staff["now"]["rows"][0]["keys"] == ["100"]
    [carols] = as_carol.json()
    assert carols["now"] == _standings(OWN_CELL)
    assert (nobody.status_code, nobody.json()["code"]) == (404, "not_found")
    assert (both.status_code, both.json()["code"]) == (422, "rejected")


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
    counted = (await client.get(f"{BOARDS}/Final")).json()
    unmarked = await client.delete(f"{MARKS}/1", headers=ORIGIN)
    await client.put(f"{MARKS}/2", headers=ORIGIN)
    overridden = (await client.get(f"{BOARDS}/Final")).json()
    clock.advance(timedelta(hours=3))
    frozen = await client.put(f"{MARKS}/1", headers=ORIGIN)

    closes = "2026-09-26T15:00:00Z"
    assert page.json()["marks"] == 1
    assert held.json() == {"numbers": [], "most": 1, "closes_at": closes, "frozen": False}
    assert marked.json() == again.json() == {**held.json(), "numbers": [1]}
    assert (over.status_code, over.json()["code"], over.json()["limit"]) == (409, "mark_limit", 1)
    assert (missing.status_code, missing.json()["code"]) == (404, "not_found")
    assert unmarked.json() == held.json()
    [row] = counted["rows"]
    assert (row["keys"], row["cells"]["sum"]["submissions"]) == (["100"], [1])
    [row] = overridden["rows"]
    assert (row["keys"], row["cells"]["sum"]["counting"]) == (["0"], False)
    assert (frozen.status_code, frozen.json()["code"]) == (403, "marks_frozen")
    assert (await client.get(MARKS)).json() == {
        "numbers": [2],
        "most": 1,
        "closes_at": closes,
        "frozen": True,
    }


async def test_a_task_no_marked_board_covers_takes_no_marks(
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
        await client.get(ORGANISE),
        await client.get(MARKS),
        await client.put(f"{MARKS}/1", headers=ORIGIN),
    ]

    assert [(answer.status_code, answer.json()["code"]) for answer in answers] == [
        (401, "unauthenticated")
    ] * 4


async def test_a_save_of_the_contests_settings_answers_the_notes_its_boards_report(
    client: httpx.AsyncClient, entered: FakeForge
) -> None:
    await sign_in_as(client, entered, 7)
    settings = await read(client, f"{CONTEST}/files/contest.yaml")
    content = re.sub(r"(?ms)^leaderboards:.*?(?=^\S|\Z)", "", settings["content"])
    late = "leaderboards:\n  - {name: Late, over: after_close, order: [points]}\n"

    written = await client.put(
        f"{CONTEST}/files/contest.yaml",
        json={"content": content.rstrip("\n") + "\n" + late, "token": settings["token"]},
        headers=ORIGIN,
    )
    organised = await client.get(ORGANISE)

    assert written.status_code == 200, written.text
    assert written.json()["notes"] == ["Late counts nothing from sum."]
    assert [board["notes"] for board in organised.json()] == [["Late counts nothing from sum."]]


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
    await _graded(client, entered, "key-0001-aaaa")
    own = (await client.get(f"{TASK}/submissions/1")).json()["grading"]
    refused = await client.get(ORGANISED, params={"user_id": 20})
    await sign_in_as(client, entered, 7)

    seen = await client.get(ORGANISED, params={"user_id": 20})

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


async def test_organisers_pick_one_row_with_such_a_submission(
    client: httpx.AsyncClient, entered: FakeForge
) -> None:
    await _graded(client, entered, "key-0001-aaaa")
    await sign_in_as(client, entered, 7)
    team = "0192f4a4-7b7e-7000-8000-000000000001"

    answers = [
        await client.get(ORGANISED),
        await client.get(ORGANISED, params={"user_id": 20, "team": team}),
        await client.get(ORGANISED, params={"user_id": 7}),
        await client.get(f"{TASK}/organise/submissions/2", params={"user_id": 20}),
        await client.get(ORGANISED, params={"team": team}),
    ]

    assert [(answer.status_code, answer.json()["code"]) for answer in answers] == [
        (422, "rejected"),
        (422, "rejected"),
        (404, "not_found"),
        (404, "not_found"),
        (404, "not_found"),
    ]
