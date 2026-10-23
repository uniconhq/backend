"""Entering a mark for a submission's value, over HTTP: the route hands
forge the task, the entrant's row, the submission's number, the value and
the mark as text, and answers the mark as it was kept; a mark forge
refuses is `invalid_mark` with its words; and a task that does not grade
by runs has no values to enter a mark for. The grading queue hands forge
the task and answers each row with its submissions, the cells that
counted each and each mark, null while missing; a task not graded by runs
has none.
"""

import uuid
from datetime import UTC, datetime
from fractions import Fraction
from typing import Any

import httpx
import pytest
from forge.api import entries
from forge.api.boards import EntrantOwner
from forge.api.errors import InvalidMark
from forge.testing import FakeForge

from tests.integration.conftest import ORIGIN, TASK, publish

AT = datetime(2026, 9, 26, 14, 0, tzinfo=UTC)
ROW = uuid.UUID("0199a2c1-6b7e-7c3a-9f10-5d2e4b8a6c31")
ENTER = f"{TASK}/organise/submissions/3/entries"
QUEUE = f"{TASK}/organise/queue"


async def test_the_route_hands_forge_the_mark_as_text_and_answers_what_was_kept(
    client: httpx.AsyncClient, sum_task: FakeForge, monkeypatch: pytest.MonkeyPatch
) -> None:
    handed: list[tuple[Any, ...]] = []

    async def enter(
        organiser: Any, task: str, owner: Any, number: int, value: str, mark: str
    ) -> entries.Entered:
        handed.append((task, owner, number, value, mark))
        return entries.Entered(value, "7.5", 7, AT)

    monkeypatch.setattr(entries, "enter", enter)

    answer = await client.post(
        ENTER,
        params={"entrant": str(ROW)},
        json={"value": "review", "mark": "7.50"},
        headers=ORIGIN,
    )

    assert answer.status_code == 200
    assert answer.json() == {
        "value": "review",
        "mark": "7.5",
        "by": 7,
        "at": "2026-09-26T14:00:00Z",
    }
    assert handed == [("acme/spring/sum", EntrantOwner(ROW), 3, "review", "7.50")]


async def test_a_mark_forge_refuses_is_invalid_mark_with_its_words(
    client: httpx.AsyncClient, sum_task: FakeForge, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def enter(*args: Any) -> entries.Entered:
        raise InvalidMark("Enter a number from 0 to 10 for review, such as 0.")

    monkeypatch.setattr(entries, "enter", enter)

    answer = await client.post(
        ENTER, params={"entrant": str(ROW)}, json={"value": "review", "mark": "11"}, headers=ORIGIN
    )

    assert (answer.status_code, answer.json()["code"]) == (422, "invalid_mark")
    assert answer.json()["detail"] == "Enter a number from 0 to 10 for review, such as 0."


async def test_a_mark_sent_as_a_number_or_too_long_is_not_read(
    client: httpx.AsyncClient, sum_task: FakeForge
) -> None:
    for body in ({"value": "review", "mark": 5}, {"value": "review", "mark": "1" * 41}):
        answer = await client.post(ENTER, params={"entrant": str(ROW)}, json=body, headers=ORIGIN)
        assert answer.status_code == 422


async def test_a_task_not_graded_by_runs_takes_no_mark(
    client: httpx.AsyncClient, sum_task: FakeForge
) -> None:
    await publish(client)

    answer = await client.post(
        ENTER, params={"entrant": str(ROW)}, json={"value": "review", "mark": "5"}, headers=ORIGIN
    )

    assert (answer.status_code, answer.json()["code"]) == (409, "not_a_run_task")


async def test_the_queue_hands_forge_the_task_and_answers_each_rows_counted_submissions(
    client: httpx.AsyncClient, sum_task: FakeForge, monkeypatch: pytest.MonkeyPatch
) -> None:
    handed: list[str] = []

    async def queue(organiser: Any, task: str) -> tuple[entries.QueueRow, ...]:
        handed.append(task)
        counted = (("gradebook", "review"), ("main", "review"))
        return (
            entries.QueueRow(
                EntrantOwner(ROW),
                "alice",
                AT,
                (
                    entries.Queued(1, counted, (("review", Fraction(15, 2)), ("style", None))),
                    entries.Queued(2, (("main", "best"),), (("review", None), ("style", None))),
                ),
            ),
        )

    monkeypatch.setattr(entries, "queue", queue)

    answer = await client.get(QUEUE, headers=ORIGIN)

    assert answer.status_code == 200
    assert answer.json() == [
        {
            "row": {"entrant": str(ROW), "name": "alice"},
            "closed_at": "2026-09-26T14:00:00Z",
            "submissions": [
                {
                    "number": 1,
                    "counted_by": [
                        {"board": "gradebook", "column": "review"},
                        {"board": "main", "column": "review"},
                    ],
                    "marks": [{"value": "review", "mark": "7.5"}, {"value": "style", "mark": None}],
                },
                {
                    "number": 2,
                    "counted_by": [{"board": "main", "column": "best"}],
                    "marks": [{"value": "review", "mark": None}, {"value": "style", "mark": None}],
                },
            ],
        }
    ]
    assert handed == ["acme/spring/sum"]


async def test_a_task_not_graded_by_runs_has_no_queue(
    client: httpx.AsyncClient, sum_task: FakeForge
) -> None:
    await publish(client)

    answer = await client.get(QUEUE, headers=ORIGIN)

    assert (answer.status_code, answer.json()["code"]) == (409, "not_a_run_task")
