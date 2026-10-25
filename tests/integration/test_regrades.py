"""What a regrade of many changed, over HTTP (#448). A rejudge answers with
the regrade it is kept as; the contest's regrades read each task's latest
one summed up by what it did to each submission, the feed read by it gives
its gradings each with the earlier and new attempt side by side, narrowed
to one change, and a manager dismisses it from the contest's page. A
regrade is read by each value and verdict it changed, as a save that
changes how the task grades shows once its runs end otherwise.
"""

import uuid
from fractions import Fraction
from typing import Any

import httpx
import pytest
from forge.api import leaderboards, regrades
from forge.api.types import PublicationId, Role, Scope, TaskId
from forge.testing import FakeForge, Setup

from tests.integration.conftest import (
    CONTEST,
    ORIGIN,
    SUM,
    TASK,
    add_task,
    edit_task,
    run_pipelines,
    sign_in_as,
    upload,
)

SOURCE = b"print(sum(map(int, input().split())))\n"
REGRADES = f"{CONTEST}/gradings/regrades"
FEED = f"{CONTEST}/gradings"


async def _submit(client: httpx.AsyncClient, forge: FakeForge, key: str) -> str:
    """A submission of acme/spring/sum by whoever is signed in; its grading."""
    made = await upload(client, forge, SOURCE)
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
    grading: str = submitted.json()["grading"]["id"]
    return grading


async def _report(client: httpx.AsyncClient, verdict: str) -> None:
    """Every pipeline started run to its report, each run ending `verdict`."""
    await run_pipelines(client, verdict)


async def test_a_rejudge_is_summed_up_and_its_gradings_read_with_what_it_changed(
    client: httpx.AsyncClient, entered: FakeForge
) -> None:
    await _submit(client, entered, "key-0001-aaaa")
    await _report(client, "accepted")
    await sign_in_as(client, entered, 7)

    rejudged = await client.post(f"{TASK}/rejudge", headers=ORIGIN)
    summed = await client.get(REGRADES)
    regrade = rejudged.json()["regrade"]
    regraded = await client.get(FEED, params={"regrade": regrade, "change": "regraded"})
    new = await client.get(FEED, params={"regrade": regrade, "change": "new"})
    unnamed = await client.get(FEED, params={"change": "regraded"})

    assert rejudged.status_code == 200, rejudged.text
    assert (rejudged.json()["queued"], rejudged.json()["over_limit"]) == (1, 0)
    assert summed.status_code == 200, summed.text
    (summary,) = summed.json()
    assert summary["id"] == regrade
    assert (summary["task"], summary["label"], summary["cause"]) == ("sum", "A", "rejudge")
    assert summary["publication"] == rejudged.json()["publication"]
    assert (summary["started_by"], summary["started_by_name"]) == (7, "ada")
    # Nothing it grades with changed, so every step's output is reused and
    # the new attempt finishes at once.
    assert (summary["total"], summary["graded"], summary["running"]) == (1, 1, False)
    assert summary["counts"] == {
        "regraded": 1,
        "new": 0,
        "running": 0,
        "failed": 0,
        "over_limit": 0,
    }
    (row,) = regraded.json()
    grading = row["grading"]
    assert (grading["attempt"], grading["regrade"], row["task"]) == (2, summary["id"], "sum")
    assert grading["change"] == {"change": "regraded", "earlier": 1, "now": 2}
    assert new.json() == [] and unnamed.json() == []

    dismissed = await client.post(f"{TASK}/regrades/{summary['id']}/dismiss", headers=ORIGIN)
    gone = await client.get(REGRADES)
    unknown = await client.post(
        f"{TASK}/regrades/0192f4a4-7b7e-7000-8000-000000000001/dismiss", headers=ORIGIN
    )

    assert dismissed.status_code == 204, dismissed.text
    assert gone.json() == []
    assert (unknown.status_code, unknown.json()["code"]) == (404, "not_found")


async def test_an_observer_reads_only_their_tasks_regrades_and_dismisses_none(
    client: httpx.AsyncClient, entered: FakeForge
) -> None:
    await _submit(client, entered, "key-0001-aaaa")
    await _report(client, "accepted")
    await sign_in_as(client, entered, 7)
    await add_task(client, "product")
    rejudged = await client.post(f"{TASK}/rejudge", headers=ORIGIN)
    regrade = rejudged.json()["regrade"]
    entered.add_user(30, "dave")
    await entered.orgs.grant_role(30, SUM, Role.OBSERVER)
    entered.add_user(31, "erin")
    await entered.orgs.grant_role(31, Scope("acme", "spring", "product"), Role.OBSERVER)

    await sign_in_as(client, entered, 30)
    seen = await client.get(REGRADES)
    dismissed = await client.post(f"{TASK}/regrades/{regrade}/dismiss", headers=ORIGIN)
    await sign_in_as(client, entered, 31)
    elsewhere = await client.get(REGRADES)
    feed = await client.get(FEED, params={"regrade": regrade})

    assert [summary["id"] for summary in seen.json()] == [regrade]
    assert (dismissed.status_code, dismissed.json()["code"]) == (403, "forbidden")
    assert (elsewhere.status_code, elsewhere.json()) == (200, [])
    assert (feed.status_code, feed.json()) == (200, [])
    await sign_in_as(client, entered, 7)
    assert [summary["id"] for summary in (await client.get(REGRADES)).json()] == [regrade]


async def test_a_run_tasks_regrade_is_read_by_each_value_and_verdict_it_changed(
    client: httpx.AsyncClient, sum_task: FakeForge, monkeypatch: pytest.MonkeyPatch
) -> None:
    regrade = uuid.UUID("0199a2c1-6b7e-7c3a-9f10-5d2e4b8a6c31")
    grading = uuid.UUID("0199a2c1-6b7e-7c3a-9f10-5d2e4b8a6c32")
    handed: list[tuple[str, uuid.UUID]] = []
    # The route serves no workspace, so any will do.
    workspace: Any = "acme/spring/@entrant.x"
    # A manager of the contest is given each leaderboard reading the task, every
    # row's place and cells before and after, what still regrades and what
    # the cell after waits on, and a leaderboard it cannot compare as unread;
    # anyone else is given null.
    entrant = uuid.UUID("0199a2c1-6b7e-7c3a-9f10-5d2e4b8a6c33")
    gradebook = regrades.LeaderboardDiff(
        leaderboard="gradebook",
        title="Gradebook",
        headers=(
            leaderboards.Header("st2", None),
            leaderboards.Header("total", 2, Fraction(0), Fraction(100), (("sum", "total"),)),
        ),
        sort=(("total", "desc"),),
        rows=(
            regrades.RowDiff(
                leaderboards.EntrantOwner(entrant),
                "carol",
                1,
                2,
                (
                    regrades.CellDiff("st2", Fraction(1), Fraction(0)),
                    regrades.CellDiff(
                        "total", Fraction(100), None, (leaderboards.Counted("sum", 4),)
                    ),
                ),
                (leaderboards.Counted("sum", 4),),
            ),
        ),
    )
    standings = regrades.LeaderboardDiff("standings", "Standings", (), (), (), unread=True)
    diffs: list[tuple[regrades.LeaderboardDiff, ...] | None] = [None, (gradebook, standings)]

    async def run_summary(organiser: Any, task: str, asked: uuid.UUID) -> regrades.RunSummary:
        handed.append((task, asked))
        return regrades.RunSummary(
            id=asked,
            task=TaskId(task),
            cause=regrades.RegradeCause.SAVE,
            publication=PublicationId("acme/spring/sum#2"),
            total=9,
            running=1,
            failed=0,
            unread=2,
            changed=(
                regrades.SubmissionChange(
                    grading=grading,
                    submission="acme/spring/@entrant.x/sum#3",
                    number=3,
                    workspace=workspace,
                    values=(regrades.ValueChange("st2", Fraction(1), Fraction(1, 3)),),
                    verdicts=(
                        regrades.VerdictChange("r4", "accepted", "wrong_answer"),
                        regrades.VerdictChange("r6", "accepted", "time_limit"),
                    ),
                    more_verdicts=7,
                ),
                regrades.SubmissionChange(
                    grading=grading,
                    submission="acme/spring/@entrant.x/sum#4",
                    number=4,
                    workspace=workspace,
                    values=(),
                    verdicts=(regrades.VerdictChange(None, "accepted", "compile_error", 30),),
                ),
            ),
            more_changed=5,
            leaderboards=diffs[len(handed) - 1],
        )

    monkeypatch.setattr(regrades, "run_summary", run_summary)

    answer = await client.get(f"{TASK}/regrades/{regrade}")
    managed = await client.get(f"{TASK}/regrades/{regrade}")

    assert answer.status_code == 200, answer.text
    assert answer.json() == {
        "id": str(regrade),
        "cause": "save",
        "publication": 2,
        "total": 9,
        "running": 1,
        "failed": 0,
        "unread": 2,
        "changed": [
            {
                "grading": str(grading),
                "number": 3,
                "values": [
                    {
                        "name": "st2",
                        "before": "1",
                        "after": "0.333333333333333333333333333333",
                        "waiting": False,
                        "text_before": None,
                        "text_after": None,
                    }
                ],
                "verdicts": [
                    {"run": "r4", "before": "accepted", "after": "wrong_answer", "runs": 1},
                    {"run": "r6", "before": "accepted", "after": "time_limit", "runs": 1},
                ],
                "more_verdicts": 7,
            },
            {
                "grading": str(grading),
                "number": 4,
                "values": [],
                "verdicts": [
                    {"run": None, "before": "accepted", "after": "compile_error", "runs": 30}
                ],
                "more_verdicts": 0,
            },
        ],
        "more_changed": 5,
        "leaderboards": None,
    }
    assert managed.json()["leaderboards"] == [
        {
            "leaderboard": "gradebook",
            "title": "Gradebook",
            "headers": [
                {
                    "name": "st2",
                    "places": None,
                    "at_least": None,
                    "at_most": None,
                    "self_reported": [],
                },
                {
                    "name": "total",
                    "places": 2,
                    "at_least": "0",
                    "at_most": "100",
                    "self_reported": [{"task": "sum", "value": "total"}],
                },
            ],
            "sort": [{"column": "total", "way": "desc"}],
            "rows": [
                {
                    "row": {"entrant": str(entrant), "name": "carol"},
                    "place_before": 1,
                    "place_after": 2,
                    "cells": [
                        {
                            "column": "st2",
                            "before": "1",
                            "after": "0",
                            "waiting": [],
                            "text_before": None,
                            "text_after": None,
                        },
                        {
                            "column": "total",
                            "before": "100",
                            "after": None,
                            "waiting": [{"task": "sum", "number": 4}],
                            "text_before": None,
                            "text_after": None,
                        },
                    ],
                    "regrading": [{"task": "sum", "number": 4}],
                }
            ],
            "unread": False,
        },
        {
            "leaderboard": "standings",
            "title": "Standings",
            "headers": [],
            "sort": [],
            "rows": [],
            "unread": True,
        },
    ]
    assert handed == [("acme/spring/sum", regrade)] * 2


async def test_a_saves_regrade_is_read_by_the_value_and_verdict_it_changed(
    client: httpx.AsyncClient, entered: FakeForge, held_setup: Setup
) -> None:
    await _submit(client, entered, "key-0001-aaaa")
    await _report(client, "accepted")
    await sign_in_as(client, entered, 7)
    await edit_task(client, "time_limit: 2", "time_limit: 1")
    await held_setup.settle()
    await _report(client, "wrong_answer")
    (summary,) = (await client.get(REGRADES)).json()

    answer = await client.get(f"{TASK}/regrades/{summary['id']}")
    unknown = await client.get(f"{TASK}/regrades/{uuid.uuid4()}")

    assert answer.status_code == 200, answer.text
    read = answer.json()
    assert (read["cause"], read["publication"], read["total"], read["running"]) == (
        "save",
        2,
        1,
        0,
    )
    (changed,) = read["changed"]
    assert changed["number"] == 1
    assert [(value["name"], value["before"], value["after"]) for value in changed["values"]] == [
        ("score", "1", "0")
    ]
    assert changed["verdicts"] == [
        {"run": "r1", "before": "accepted", "after": "wrong_answer", "runs": 1}
    ]
    assert (unknown.status_code, unknown.json()["code"]) == (404, "not_found")
