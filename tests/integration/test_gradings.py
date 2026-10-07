"""An organiser's view of and controls over a task's gradings, over HTTP:
the list, newest first with each one's reason, to an observer; cancelling a
grading that reads as a system error with a sentence its contestant then
reads, and refusing one that is not, a sentence that is not one and an
earlier attempt; retrying a finished one as a new attempt, and one still
being graded refused; a rejudge queuing a new attempt of every submission's
latest grading; and a grading's run log, none for one not yet run. A
contestant is refused all five, a grading named under another task's prefix
is no such grading, whatever the caller may do at either task, and the
manager role itself is held to the guard's table.
"""

import uuid
from datetime import timedelta

import httpx
import pytest
from forge.api.types import Role, Scope
from forge.testing import FakeClock, FakeForge, Setup, name_places

from tests.integration.conftest import CONTEST, ORIGIN, TASK, sign_in_as, upload

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
    listed = await client.get(f"{TASK}/gradings")
    await sign_in_as(client, entered, 20)
    mine = await client.get(f"{TASK}/submissions/1")

    assert (waiting.status_code, waiting.json()["code"]) == (409, "wrong_status")
    assert waiting.json()["current"] == "dispatched"
    assert (unsaid.status_code, unsaid.json()["code"]) == (422, "invalid_reason")
    assert (no_body.status_code, no_body.json()["code"]) == (422, "validation_error")
    assert cancelled.status_code == 200, cancelled.text
    body = cancelled.json()
    assert (body["id"], body["status"], body["attempt"]) == (grading, "cancelled", 1)
    assert body["cancel_reason"] == REASON["reason"]
    assert body["error"]
    assert (body["submission_number"], body["result"]) == (1, None)
    assert body["finished_at"] is not None
    assert (again.status_code, again.json()["current"]) == (409, "cancelled")
    assert listed.json()[0]["cancel_reason"] == REASON["reason"]
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


async def test_a_manager_retries_a_stuck_grading_and_cancels_only_the_latest_attempt(
    client: httpx.AsyncClient, entered: FakeForge, clock: FakeClock
) -> None:
    grading = await _grading(client, entered)
    await sign_in_as(client, entered, 7)

    retried_early = await client.post(f"{TASK}/gradings/{grading}/retry", headers=ORIGIN)
    clock.advance(STUCK)
    retried = await client.post(f"{TASK}/gradings/{grading}/retry", headers=ORIGIN)
    earlier = await client.post(f"{TASK}/gradings/{grading}/cancel", json=REASON, headers=ORIGIN)
    await sign_in_as(client, entered, 20)
    mine = await client.get(f"{TASK}/submissions/1")

    assert (retried_early.status_code, retried_early.json()["code"]) == (409, "wrong_status")
    assert retried_early.json()["current"] == "dispatched"
    assert retried.status_code == 200, retried.text
    assert (retried.json()["attempt"], retried.json()["status"]) == (2, "queued")
    assert retried.json()["id"] != grading
    assert (earlier.status_code, earlier.json()["code"]) == (409, "conflict")
    latest = mine.json()["grading"]
    assert (latest["attempt"], latest["status"]) == (2, "dispatched")


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
    assert [(row["id"], row["attempt"]) for row in listed.json()] == [
        (retried.json()["id"], 2),
        (grading, 1),
    ]
    assert [row["status"] for row in listed.json()] == ["dispatched", "system_error"]
    assert listed.json()[1]["error"]
    assert [row["cancel_reason"] for row in listed.json()] == [None, None]
    assert [row["id"] for row in one.json()] == [retried.json()["id"]]
    assert too_many.status_code == 422


async def test_a_rejudge_grades_every_submission_again(
    client: httpx.AsyncClient, entered: FakeForge
) -> None:
    await _grading(client, entered)
    await sign_in_as(client, entered, 7)

    rejudged = await client.post(f"{TASK}/rejudge", headers=ORIGIN)

    assert rejudged.status_code == 200, rejudged.text
    body = rejudged.json()
    assert (body["queued"], body["cancelled"], body["left_running"]) == (0, 0, 1)
    assert body["publication"]


async def test_a_contestant_is_refused_every_control(
    client: httpx.AsyncClient, entered: FakeForge
) -> None:
    grading = await _grading(client, entered)

    answers = [
        await client.get(f"{TASK}/gradings"),
        await client.get(f"{TASK}/gradings/{grading}/log"),
        await client.post(f"{TASK}/gradings/{grading}/cancel", json=REASON, headers=ORIGIN),
        await client.post(f"{TASK}/gradings/{grading}/retry", headers=ORIGIN),
        await client.post(f"{TASK}/rejudge", headers=ORIGIN),
    ]

    assert [(answer.status_code, answer.json()["code"]) for answer in answers] == [
        (403, "forbidden")
    ] * 5


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
        await client.post(f"{TASK}/rejudge", headers=ORIGIN),
    ]

    assert [(answer.status_code, answer.json()["code"]) for answer in answers] == [
        (401, "unauthenticated")
    ] * 5
