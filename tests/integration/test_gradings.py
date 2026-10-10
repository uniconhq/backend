"""An organiser's view of and controls over a task's gradings, over HTTP:
the list, newest first with each one's reason, who submitted it and whether
it is its submission's latest attempt, to an observer; cancelling a grading
that reads as a system error with a sentence its contestant then reads, and
refusing one that is not, a sentence that is not one and an earlier
attempt; retrying a finished one as a new attempt, and refusing one still
being graded, an earlier attempt and a submission staff cancelled; having a
broken grading's submission count as its last good result, refusing one
that is not broken, and taking that back; a rejudge, and a save that
changes how the task grades, queuing a new attempt of every submission's
latest grading; and a grading's run log, none for one not yet run. A
contestant is refused all seven, a grading named under
another task's prefix is no such grading, whatever the caller may do at
either task, and the manager role itself is held to the guard's table.
"""

import uuid
from datetime import timedelta
from urllib.parse import urlsplit

import httpx
import pytest
from forge.api.types import Role, Scope
from forge.testing import FakeClock, FakeForge, Setup, name_places

from tests.integration.conftest import CONTEST, ORIGIN, TASK, read, sign_in_as, upload

SOURCE = b"print(sum(map(int, input().split())))\n"
FINISHED = (
    b'{"event": "finished", "result": {"schema_version": 5, "stopped": null, '
    b'"stopped_by": null, "tests": [{"test": "main/1", "outcome": "accepted", '
    b'"values": {"time_ms": 12}}], "values": {"log": ""}, "run_log": null, "error": null}}'
)
"""A finished report with one accepted test and no run log."""
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
                "submission": {"uploads": [made["id"]]},
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
        "dispatched",
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
    assert (latest["attempt"], latest["status"]) == (2, "dispatched")


async def _graded(client: httpx.AsyncClient, forge: FakeForge) -> str:
    """carol's first submission of acme/spring/sum, its run finished with a
    result; its grading's id.
    """
    grading = await _grading(client, forge)
    [run] = forge.ci.runs.values()
    parts = urlsplit(run.variables["UNICON_ENVELOPE_URL"])
    envelope = (await client.get(f"{parts.path}?{parts.query}")).json()
    reported = await client.post(
        urlsplit(envelope["callback"]["url"]).path,
        content=FINISHED,
        headers={"Authorization": f"Bearer {envelope['callback']['token']}"},
    )
    assert reported.status_code == 200, reported.text
    return grading


async def test_a_manager_falls_back_to_a_broken_gradings_last_good_result_and_clears_it(
    client: httpx.AsyncClient, entered: FakeForge, clock: FakeClock
) -> None:
    first = await _graded(client, entered)
    await sign_in_as(client, entered, 7)
    second = (await client.post(f"{TASK}/gradings/{first}/retry", headers=ORIGIN)).json()["id"]
    clock.advance(STUCK)

    done = await client.put(f"{TASK}/gradings/{first}/fallback", headers=ORIGIN)
    fell = await client.put(f"{TASK}/gradings/{second}/fallback", headers=ORIGIN)
    listed = await client.get(f"{TASK}/gradings")
    await sign_in_as(client, entered, 20)
    counted = (await client.get(f"{TASK}/submissions/1")).json()["grading"]
    await sign_in_as(client, entered, 7)
    cleared = await client.delete(f"{TASK}/gradings/{second}/fallback", headers=ORIGIN)
    await sign_in_as(client, entered, 20)
    waiting = (await client.get(f"{TASK}/submissions/1")).json()["grading"]

    assert (done.status_code, done.json()["code"], done.json()["current"]) == (
        409,
        "wrong_status",
        "done",
    )
    assert fell.status_code == 200, fell.text
    assert (fell.json()["status"], fell.json()["attempt"]) == ("system_error", 2)
    assert (fell.json()["last_good"], fell.json()["fallback"], fell.json()["falls_back"]) == (
        1,
        "staff",
        True,
    )
    rows = [entry["grading"] for entry in listed.json()]
    assert [(row["attempt"], row["last_good"], row["fallback"]) for row in rows] == [
        (2, 1, "staff"),
        (1, None, None),
    ]
    assert (counted["attempt"], counted["status"]) == (1, "done")
    assert cleared.status_code == 200, cleared.text
    assert (cleared.json()["last_good"], cleared.json()["fallback"]) == (1, None)
    assert waiting["attempt"] == 2


async def test_a_fallback_is_refused_with_no_earlier_result_and_on_an_earlier_attempt(
    client: httpx.AsyncClient, entered: FakeForge, clock: FakeClock
) -> None:
    grading = await _grading(client, entered)
    await sign_in_as(client, entered, 7)
    clock.advance(STUCK)

    nothing = await client.put(f"{TASK}/gradings/{grading}/fallback", headers=ORIGIN)
    await client.post(f"{TASK}/gradings/{grading}/retry", headers=ORIGIN)
    earlier = await client.put(f"{TASK}/gradings/{grading}/fallback", headers=ORIGIN)

    assert (nothing.status_code, nothing.json()["code"]) == (409, "conflict")
    assert "No earlier attempt" in nothing.json()["detail"]
    assert (earlier.status_code, earlier.json()["code"]) == (409, "conflict")
    assert "later attempt" in earlier.json()["detail"]


async def test_under_the_contests_last_result_a_cancelled_grading_keeps_its_last_good_result(
    client: httpx.AsyncClient, entered: FakeForge, clock: FakeClock
) -> None:
    first = await _graded(client, entered)
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
    assert written.status_code == 200, written.text
    second = (await client.post(f"{TASK}/gradings/{first}/retry", headers=ORIGIN)).json()["id"]
    clock.advance(STUCK)

    cancelled = await client.post(f"{TASK}/gradings/{second}/cancel", json=REASON, headers=ORIGIN)
    await sign_in_as(client, entered, 20)
    counted = (await client.get(f"{TASK}/submissions/1")).json()["grading"]

    assert cancelled.status_code == 200, cancelled.text
    body = cancelled.json()
    assert (body["status"], body["last_good"], body["fallback"], body["falls_back"]) == (
        "cancelled",
        1,
        "contest",
        False,
    )
    assert (counted["attempt"], counted["status"]) == (1, "done")


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
    assert [entry["by"]["name"] for entry in listed.json()] == ["carol", "carol"]
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


async def test_a_save_that_changes_how_the_task_grades_says_how_many_it_regraded(
    client: httpx.AsyncClient, entered: FakeForge
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
    assert (body["grading_changed"], body["regraded"]) == (True, 1)
    assert body["notes"] == [
        "Each group's most points: main 100.",
        "sum reveals at 2026-09-26T15:00:00+00:00.",
        "This save moves Standings.",
    ]


async def test_a_contestant_is_refused_every_control(
    client: httpx.AsyncClient, entered: FakeForge
) -> None:
    grading = await _grading(client, entered)

    answers = [
        await client.get(f"{TASK}/gradings"),
        await client.get(f"{TASK}/gradings/{grading}/log"),
        await client.post(f"{TASK}/gradings/{grading}/cancel", json=REASON, headers=ORIGIN),
        await client.post(f"{TASK}/gradings/{grading}/retry", headers=ORIGIN),
        await client.put(f"{TASK}/gradings/{grading}/fallback", headers=ORIGIN),
        await client.delete(f"{TASK}/gradings/{grading}/fallback", headers=ORIGIN),
        await client.post(f"{TASK}/rejudge", headers=ORIGIN),
    ]

    assert [(answer.status_code, answer.json()["code"]) for answer in answers] == [
        (403, "forbidden")
    ] * 7


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
    assert mine.json()["grading"]["status"] == "dispatched"


@pytest.mark.parametrize(
    "scope",
    [Scope("acme", "spring", "product"), Scope("acme", "spring")],
    ids=["observing the other task alone", "observing both tasks"],
)
async def test_a_log_named_under_another_task_is_no_such_grading(
    client: httpx.AsyncClient, entered: FakeForge, held_setup: Setup, scope: Scope
) -> None:
    await name_places(held_setup, "acme/spring/product")
    grading = await _grading(client, entered)
    await entered.orgs.grant_role(8, scope, Role.OBSERVER)
    await sign_in_as(client, entered, 8)
    product = f"{CONTEST}/tasks/product"

    foreign = await client.get(f"{product}/gradings/{grading}/log")
    nobodys = await client.get(f"{product}/gradings/{uuid.uuid4()}/log")

    assert (foreign.status_code, foreign.json()["code"]) == (404, "not_found")
    assert foreign.json() == nobodys.json()


async def test_a_grading_not_yet_run_has_no_log(
    client: httpx.AsyncClient, entered: FakeForge
) -> None:
    grading = await _grading(client, entered)
    await sign_in_as(client, entered, 7)

    missing = await client.get(f"{TASK}/gradings/{grading}/log")

    assert (missing.status_code, missing.json()["code"]) == (404, "not_found")


async def test_the_controls_need_a_session(client: httpx.AsyncClient, entered: FakeForge) -> None:
    grading = await _grading(client, entered)
    client.cookies.clear()

    answers = [
        await client.get(f"{TASK}/gradings"),
        await client.get(f"{TASK}/gradings/{grading}/log"),
        await client.post(f"{TASK}/gradings/{grading}/cancel", json=REASON, headers=ORIGIN),
        await client.post(f"{TASK}/gradings/{grading}/retry", headers=ORIGIN),
        await client.put(f"{TASK}/gradings/{grading}/fallback", headers=ORIGIN),
        await client.delete(f"{TASK}/gradings/{grading}/fallback", headers=ORIGIN),
        await client.post(f"{TASK}/rejudge", headers=ORIGIN),
    ]

    assert [(answer.status_code, answer.json()["code"]) for answer in answers] == [
        (401, "unauthenticated")
    ] * 7
