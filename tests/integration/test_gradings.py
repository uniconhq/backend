"""An organiser's view of and controls over a task's gradings, over HTTP:
the list, newest first with each one's reason, who submitted it and whether
it is its submission's latest attempt, to an observer; cancelling a grading
that reads as a system error with a sentence its contestant then reads, and
refusing one that is not, a sentence that is not one and an earlier
attempt; retrying a finished one as a new attempt, which reuses what its
steps did and finishes at once, and refusing one still being graded, an
earlier attempt and a submission staff cancelled; a failed or cancelled
later attempt leaving the submission at its last result, one with none
read as delayed, and a contest that says otherwise refused; a rejudge
queuing a new attempt of every submission's latest grading, and a save
that changes how the task grades doing so once its check passes. A
contestant is refused all four, a grading named under another task's prefix
is no such grading, whatever the caller may do at either task, and the
manager role itself is held to the guard's table.
"""

import uuid
from datetime import timedelta

import httpx
import pytest
from forge.api.types import Role, Scope
from forge.testing import FakeClock, FakeForge, Setup, name_places

from tests.integration.conftest import (
    CONTEST,
    ORIGIN,
    TASK,
    edit_task,
    read,
    run_pipelines,
    sign_in_as,
    upload,
)

SOURCE = b"print(sum(map(int, input().split())))\n"
REASON = {"reason": "The checker crashed on this one; it is not counted."}
STUCK = timedelta(hours=2)
"""How long a dispatched grading waits for a machine before it reads as a
system error."""


async def _grading(client: httpx.AsyncClient, forge: FakeForge) -> str:
    """carol's first submission of acme/spring/sum, queued; its grading's id."""
    made = await upload(client, forge, SOURCE)
    submitted = await client.post(
        f"{TASK}/submissions",
        json={
            "idempotency_key": "key-0001-aaaa",
            "inputs": {
                "code": {"uploads": [made["id"]]},
                "language": {"value": "python"},
            },
        },
        headers=ORIGIN,
    )
    grading: str = submitted.json()["grading"]["id"]
    return grading


async def test_a_manager_cancels_a_grading_in_system_error_saying_why(
    client: httpx.AsyncClient, entered: FakeForge, clock: FakeClock
) -> None:
    grading = await _grading(client, entered)
    await sign_in_as(client, entered, 7)
    cancel = f"{TASK}/gradings/{grading}/cancel"

    waiting = await client.post(cancel, json=REASON, headers=ORIGIN)
    clock.advance(STUCK)
    unsaid = await client.post(cancel, json={"reason": "  "}, headers=ORIGIN)
    no_body = await client.post(cancel, headers=ORIGIN)
    cancelled = await client.post(cancel, json=REASON, headers=ORIGIN)
    again = await client.post(cancel, json=REASON, headers=ORIGIN)
    retried = await client.post(f"{TASK}/gradings/{grading}/retry", headers=ORIGIN)
    listed = await client.get(f"{TASK}/gradings")
    await sign_in_as(client, entered, 20)
    mine = await client.get(f"{TASK}/submissions/1")

    assert (waiting.status_code, waiting.json()["code"]) == (409, "wrong_status")
    assert waiting.json()["current"] == "dispatched"
    assert (unsaid.status_code, unsaid.json()["code"]) == (422, "invalid_reason")
    assert (no_body.status_code, no_body.json()["code"]) == (422, "validation_error")
    assert cancelled.status_code == 200, cancelled.text
    body = cancelled.json()
    assert (body["id"], body["status"], body["attempt"], body["latest"]) == (
        grading,
        "cancelled",
        1,
        True,
    )
    assert body["cancel_reason"] == REASON["reason"]
    assert body["error"]
    assert (body["submission_number"], body["result"]) == (1, None)
    assert body["finished_at"] is not None
    assert (again.status_code, again.json()["current"]) == (409, "cancelled")
    assert (retried.status_code, retried.json()["code"]) == (409, "wrong_status")
    assert retried.json()["current"] == "cancelled"
    assert listed.json()[0]["grading"]["cancel_reason"] == REASON["reason"]
    assert mine.json()["grading"]["status"] == "cancelled"
    assert mine.json()["grading"]["reason"] == REASON["reason"]


async def test_a_grading_being_run_tells_its_contestant_no_reason(
    client: httpx.AsyncClient, entered: FakeForge
) -> None:
    await _grading(client, entered)

    mine = await client.get(f"{TASK}/submissions/1")

    assert (mine.json()["grading"]["status"], mine.json()["grading"]["reason"]) == (
        "grading",
        None,
    )


async def test_a_manager_retries_a_stuck_grading_and_acts_only_on_the_latest_attempt(
    client: httpx.AsyncClient, entered: FakeForge, clock: FakeClock
) -> None:
    grading = await _grading(client, entered)
    await sign_in_as(client, entered, 7)

    retried_early = await client.post(f"{TASK}/gradings/{grading}/retry", headers=ORIGIN)
    clock.advance(STUCK)
    retried = await client.post(f"{TASK}/gradings/{grading}/retry", headers=ORIGIN)
    earlier = await client.post(f"{TASK}/gradings/{grading}/cancel", json=REASON, headers=ORIGIN)
    retried_earlier = await client.post(f"{TASK}/gradings/{grading}/retry", headers=ORIGIN)
    await sign_in_as(client, entered, 20)
    mine = await client.get(f"{TASK}/submissions/1")

    assert (retried_early.status_code, retried_early.json()["code"]) == (409, "wrong_status")
    assert retried_early.json()["current"] == "dispatched"
    assert retried.status_code == 200, retried.text
    assert (retried.json()["attempt"], retried.json()["status"]) == (2, "queued")
    assert retried.json()["id"] != grading
    assert (earlier.status_code, earlier.json()["code"]) == (409, "conflict")
    assert (retried_earlier.status_code, retried_earlier.json()["code"]) == (409, "conflict")
    assert "later attempt" in retried_earlier.json()["detail"]
    latest = mine.json()["grading"]
    assert (latest["attempt"], latest["status"]) == (2, "grading")


async def _graded(client: httpx.AsyncClient, forge: FakeForge) -> str:
    """carol's first submission of acme/spring/sum, its run finished with a
    result; its grading's id.
    """
    grading = await _grading(client, forge)
    await run_pipelines(client)
    return grading


async def _regrading(client: httpx.AsyncClient, forge: FakeForge, setup: Setup) -> str:
    """carol's first submission graded, and then graded again by ada's save
    of a shorter time limit, its second attempt not yet run; ada signed in.
    Its id.
    """
    await _graded(client, forge)
    await sign_in_as(client, forge, 7)
    await edit_task(client, "time_limit: 2", "time_limit: 1")
    await setup.settle()
    second: str = (await client.get(f"{TASK}/gradings")).json()[0]["grading"]["id"]
    return second


async def test_a_retry_of_a_graded_submission_reuses_what_its_steps_did(
    client: httpx.AsyncClient, entered: FakeForge
) -> None:
    first = await _graded(client, entered)
    await sign_in_as(client, entered, 7)

    retried = await client.post(f"{TASK}/gradings/{first}/retry", headers=ORIGIN)
    listed = await client.get(f"{TASK}/gradings")

    assert retried.status_code == 200, retried.text
    rows = [entry["grading"] for entry in listed.json()]
    assert [(row["attempt"], row["status"], row["latest"]) for row in rows] == [
        (2, "done", True),
        (1, "done", False),
    ]


async def test_a_failed_later_attempt_leaves_the_submission_at_its_last_result_and_says_which(
    client: httpx.AsyncClient, entered: FakeForge, clock: FakeClock, held_setup: Setup
) -> None:
    second = await _regrading(client, entered, held_setup)
    clock.advance(STUCK)

    listed = await client.get(f"{TASK}/gradings")
    gone = await client.put(f"{TASK}/gradings/{second}/fallback", headers=ORIGIN)
    await sign_in_as(client, entered, 20)
    counted = (await client.get(f"{TASK}/submissions/1")).json()["grading"]

    rows = [entry["grading"] for entry in listed.json()]
    assert [
        (row["attempt"], row["status"], row["last_good"], row["automatic"]) for row in rows
    ] == [(2, "system_error", 1, False), (1, "done", None, False)]
    assert "fallback" not in rows[0] and "falls_back" not in rows[0]
    assert gone.status_code in (404, 405)
    assert (counted["attempt"], counted["status"]) == (1, "graded")


async def test_a_submission_with_no_result_whose_grading_failed_reads_as_delayed(
    client: httpx.AsyncClient, entered: FakeForge, clock: FakeClock
) -> None:
    await _grading(client, entered)
    clock.advance(STUCK)

    mine = (await client.get(f"{TASK}/submissions/1")).json()["grading"]
    await sign_in_as(client, entered, 7)
    (listed,) = (await client.get(f"{TASK}/gradings")).json()

    assert (mine["status"], mine["reason"], mine["runs"]) == ("delayed", None, [])
    assert (listed["grading"]["status"], listed["grading"]["last_good"]) == ("system_error", None)


async def test_a_cancel_after_a_result_keeps_the_result(
    client: httpx.AsyncClient, entered: FakeForge, clock: FakeClock, held_setup: Setup
) -> None:
    second = await _regrading(client, entered, held_setup)
    clock.advance(STUCK)

    cancelled = await client.post(f"{TASK}/gradings/{second}/cancel", json=REASON, headers=ORIGIN)
    await sign_in_as(client, entered, 20)
    counted = (await client.get(f"{TASK}/submissions/1")).json()["grading"]

    assert cancelled.status_code == 200, cancelled.text
    assert (cancelled.json()["status"], cancelled.json()["last_good"]) == ("cancelled", 1)
    assert (counted["attempt"], counted["status"]) == (1, "graded")


async def test_a_contest_that_says_what_a_failed_grading_counts_as_is_refused_naming_it(
    client: httpx.AsyncClient, entered: FakeForge
) -> None:
    await sign_in_as(client, entered, 7)
    settings = await read(client, f"{CONTEST}/files/contest.yaml")

    written = await client.put(
        f"{CONTEST}/files/contest.yaml",
        json={
            "encoding": "utf-8",
            "content": settings["content"] + "on_system_error: last_result\n",
            "token": settings["token"],
        },
        headers=ORIGIN,
    )

    assert (written.status_code, written.json()["code"]) == (422, "invalid_definition")
    assert [problem["path"] for problem in written.json()["errors"]] == ["on_system_error"]
    assert "tried again once by itself" in written.json()["errors"][0]["message"]


async def test_an_observer_lists_the_tasks_gradings_newest_first_with_their_reasons(
    client: httpx.AsyncClient, entered: FakeForge, clock: FakeClock
) -> None:
    grading = await _grading(client, entered)
    await sign_in_as(client, entered, 7)
    clock.advance(STUCK)
    retried = await client.post(f"{TASK}/gradings/{grading}/retry", headers=ORIGIN)

    listed = await client.get(f"{TASK}/gradings")
    one = await client.get(f"{TASK}/gradings", params={"limit": 1})
    too_many = await client.get(f"{TASK}/gradings", params={"limit": 501})

    assert listed.status_code == 200, listed.text
    rows = [entry["grading"] for entry in listed.json()]
    assert [(row["id"], row["attempt"], row["latest"]) for row in rows] == [
        (retried.json()["id"], 2, True),
        (grading, 1, False),
    ]
    assert [row["status"] for row in rows] == ["dispatched", "system_error"]
    assert rows[1]["error"]
    assert [row["cancel_reason"] for row in rows] == [None, None]
    assert [(entry["task"], entry["label"]) for entry in listed.json()] == [("sum", "A")] * 2
    assert [entry["by"]["username"] for entry in listed.json()] == ["carol", "carol"]
    assert [entry["grading"]["id"] for entry in one.json()] == [retried.json()["id"]]
    assert too_many.status_code == 422


async def test_a_rejudge_grades_every_submission_again(
    client: httpx.AsyncClient, entered: FakeForge, clock: FakeClock
) -> None:
    grading = await _grading(client, entered)
    await sign_in_as(client, entered, 7)
    clock.advance(STUCK)

    rejudged = await client.post(f"{TASK}/rejudge", headers=ORIGIN)
    listed = await client.get(f"{TASK}/gradings")

    assert rejudged.status_code == 200, rejudged.text
    body = rejudged.json()
    assert (body["queued"], body["cancelled"], body["left_running"]) == (1, 0, 0)
    rows = [entry["grading"] for entry in listed.json()]
    assert [(row["attempt"], row["latest"]) for row in rows] == [(2, True), (1, False)]
    assert rows[1]["id"] == grading
    assert rows[0]["publication"] == body["publication"]


async def test_a_rejudge_leaves_a_grading_against_the_current_publication_to_finish(
    client: httpx.AsyncClient, entered: FakeForge
) -> None:
    await _grading(client, entered)
    await sign_in_as(client, entered, 7)

    rejudged = await client.post(f"{TASK}/rejudge", headers=ORIGIN)

    assert rejudged.status_code == 200, rejudged.text
    body = rejudged.json()
    assert (body["queued"], body["cancelled"], body["left_running"]) == (0, 0, 1)


async def test_a_save_that_changes_how_the_task_grades_regrades_once_its_check_passes(
    client: httpx.AsyncClient, entered: FakeForge, held_setup: Setup
) -> None:
    await _grading(client, entered)
    await sign_in_as(client, entered, 7)
    task = await read(client, f"{TASK}/files/task.yaml")

    saved = await client.put(
        f"{TASK}/files/task.yaml",
        json={
            "content": task["content"].replace("time_limit: 2", "time_limit: 1"),
            "token": task["token"],
            "confirm": True,
        },
        headers=ORIGIN,
    )

    assert saved.status_code == 200, saved.text
    body = saved.json()
    assert (body["grading_changed"], body["check"]) == (True, "checking")
    # The publication is checked before it takes over, and only then are
    # the submissions graded again.
    assert (body["regraded"], body["regrade"]) == (0, None)
    assert body["effect"]["runs_again"] == [
        "Once the save's check passes, 1 submission is graded again, running solution and "
        "compare again: the inputs of the step solution changed."
    ]
    assert body["effect"]["scores"] == ["No score changes."]
    await run_pipelines(client, pipelines=("save",))
    await held_setup.settle()
    [regrade] = (await client.get(f"{CONTEST}/gradings/regrades")).json()
    assert (regrade["cause"], regrade["publication"], regrade["total"]) == ("save", 2, 1)
    rows = [entry["grading"] for entry in (await client.get(f"{TASK}/gradings")).json()]
    assert [(row["attempt"], row["regrade"]) for row in rows] == [
        (2, regrade["id"]),
        (1, None),
    ]


async def test_a_contestant_is_refused_every_control(
    client: httpx.AsyncClient, entered: FakeForge
) -> None:
    grading = await _grading(client, entered)

    answers = [
        await client.get(f"{TASK}/gradings"),
        await client.post(f"{TASK}/gradings/{grading}/cancel", json=REASON, headers=ORIGIN),
        await client.post(f"{TASK}/gradings/{grading}/retry", headers=ORIGIN),
        await client.post(f"{TASK}/rejudge", headers=ORIGIN),
    ]

    assert [(answer.status_code, answer.json()["code"]) for answer in answers] == [
        (403, "forbidden")
    ] * 4


@pytest.mark.parametrize(
    "scope",
    [Scope("acme", "spring", "product"), Scope("acme", "spring")],
    ids=["managing the other task alone", "managing both tasks"],
)
@pytest.mark.parametrize("control", ["cancel", "retry"])
async def test_a_grading_named_under_another_task_is_no_such_grading(
    client: httpx.AsyncClient, entered: FakeForge, held_setup: Setup, scope: Scope, control: str
) -> None:
    await name_places(held_setup, "acme/spring/product")
    grading = await _grading(client, entered)
    await entered.orgs.grant_role(8, scope, Role.MANAGER)
    await sign_in_as(client, entered, 8)
    product = f"{CONTEST}/tasks/product"

    foreign = await client.post(
        f"{product}/gradings/{grading}/{control}", json=REASON, headers=ORIGIN
    )
    nobodys = await client.post(
        f"{product}/gradings/{uuid.uuid4()}/{control}", json=REASON, headers=ORIGIN
    )
    await sign_in_as(client, entered, 20)
    mine = await client.get(f"{TASK}/submissions/1")

    assert (foreign.status_code, foreign.json()["code"]) == (404, "not_found")
    assert foreign.json() == nobodys.json()
    assert mine.json()["grading"]["status"] == "grading"


async def test_the_controls_need_a_session(client: httpx.AsyncClient, entered: FakeForge) -> None:
    grading = await _grading(client, entered)
    client.cookies.clear()

    answers = [
        await client.get(f"{TASK}/gradings"),
        await client.post(f"{TASK}/gradings/{grading}/cancel", json=REASON, headers=ORIGIN),
        await client.post(f"{TASK}/gradings/{grading}/retry", headers=ORIGIN),
        await client.post(f"{TASK}/rejudge", headers=ORIGIN),
    ]

    assert [(answer.status_code, answer.json()["code"]) for answer in answers] == [
        (401, "unauthenticated")
    ] * 4
