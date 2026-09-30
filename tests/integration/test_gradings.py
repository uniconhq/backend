"""An organiser's controls over a task's gradings, over HTTP: cancelling a
queued grading, and a finished one refused with its status; retrying a
finished one as a new attempt, and one still being graded refused; and a
rejudge queuing a new attempt of every submission's latest grading. A
contestant is refused all three, a grading named under another task's prefix
is no such grading, whatever the caller may do at either task, and the
manager role itself is held to the guard's table.
"""

import uuid

import httpx
import pytest
from forge.api.types import Role, Scope
from forge.testing import FakeForge

from tests.integration.conftest import CONTEST, ORIGIN, TASK, sign_in_as, upload

SOURCE = b"print(sum(map(int, input().split())))\n"


async def _grading(client: httpx.AsyncClient, forge: FakeForge) -> str:
    """carol's first submission of acme/spring/sum, queued; its grading's id."""
    made = await upload(client, forge, SOURCE)
    submitted = await client.post(
        f"{TASK}/submissions",
        json={
            "idempotency_key": "key-0001-aaaa",
            "inputs": {"submission": {"uploads": [made["id"]], "language": "python"}},
        },
        headers=ORIGIN,
    )
    grading: str = submitted.json()["gradings"][0]["id"]
    return grading


async def test_a_manager_cancels_and_retries_a_grading(
    client: httpx.AsyncClient, entered: FakeForge
) -> None:
    grading = await _grading(client, entered)
    await sign_in_as(client, entered, 7)

    retried_early = await client.post(f"{TASK}/gradings/{grading}/retry", headers=ORIGIN)
    cancelled = await client.post(f"{TASK}/gradings/{grading}/cancel", headers=ORIGIN)
    again = await client.post(f"{TASK}/gradings/{grading}/cancel", headers=ORIGIN)
    retried = await client.post(f"{TASK}/gradings/{grading}/retry", headers=ORIGIN)
    await sign_in_as(client, entered, 20)
    mine = await client.get(f"{TASK}/submissions/1")

    assert (retried_early.status_code, retried_early.json()["code"]) == (409, "wrong_status")
    assert retried_early.json()["current"] == "queued"
    assert cancelled.status_code == 200, cancelled.text
    body = cancelled.json()
    assert (body["id"], body["status"], body["attempt"]) == (grading, "cancelled", 1)
    assert (body["submission_number"], body["stage"]) == (1, "default")
    assert body["finished_at"] is not None
    assert (again.status_code, again.json()["current"]) == (409, "cancelled")
    assert retried.status_code == 200, retried.text
    assert (retried.json()["attempt"], retried.json()["status"]) == (2, "queued")
    assert retried.json()["id"] != grading
    [latest] = mine.json()["gradings"]
    assert (latest["attempt"], latest["status"]) == (2, "queued")


async def test_a_rejudge_grades_every_submission_again(
    client: httpx.AsyncClient, entered: FakeForge
) -> None:
    grading = await _grading(client, entered)
    await sign_in_as(client, entered, 7)
    await client.post(f"{TASK}/gradings/{grading}/cancel", headers=ORIGIN)

    rejudged = await client.post(f"{TASK}/rejudge", headers=ORIGIN)

    assert rejudged.status_code == 200, rejudged.text
    body = rejudged.json()
    assert (body["queued"], body["cancelled"], body["left_running"], body["passed_over"]) == (
        1,
        0,
        0,
        0,
    )
    assert body["publication"]


async def test_a_contestant_is_refused_every_control(
    client: httpx.AsyncClient, entered: FakeForge
) -> None:
    grading = await _grading(client, entered)

    answers = [
        await client.post(f"{TASK}/gradings/{grading}/cancel", headers=ORIGIN),
        await client.post(f"{TASK}/gradings/{grading}/retry", headers=ORIGIN),
        await client.post(f"{TASK}/rejudge", headers=ORIGIN),
    ]

    assert [(answer.status_code, answer.json()["code"]) for answer in answers] == [
        (403, "forbidden")
    ] * 3


@pytest.mark.parametrize(
    "scope",
    [Scope("acme", "spring", "product"), Scope("acme", "spring")],
    ids=["managing the other task alone", "managing both tasks"],
)
@pytest.mark.parametrize("control", ["cancel", "retry"])
async def test_a_grading_named_under_another_task_is_no_such_grading(
    client: httpx.AsyncClient, entered: FakeForge, scope: Scope, control: str
) -> None:
    grading = await _grading(client, entered)
    await entered.orgs.grant_role(8, scope, Role.MANAGER)
    await sign_in_as(client, entered, 8)
    product = f"{CONTEST}/tasks/product"

    foreign = await client.post(f"{product}/gradings/{grading}/{control}", headers=ORIGIN)
    nobodys = await client.post(f"{product}/gradings/{uuid.uuid4()}/{control}", headers=ORIGIN)
    await sign_in_as(client, entered, 20)
    mine = await client.get(f"{TASK}/submissions/1")

    assert (foreign.status_code, foreign.json()["code"]) == (404, "not_found")
    assert foreign.json() == nobodys.json()
    assert mine.json()["gradings"][0]["status"] == "queued"


async def test_the_controls_need_a_session(client: httpx.AsyncClient, entered: FakeForge) -> None:
    grading = await _grading(client, entered)
    client.cookies.clear()

    answers = [
        await client.post(f"{TASK}/gradings/{grading}/cancel", headers=ORIGIN),
        await client.post(f"{TASK}/gradings/{grading}/retry", headers=ORIGIN),
        await client.post(f"{TASK}/rejudge", headers=ORIGIN),
    ]

    assert [(answer.status_code, answer.json()["code"]) for answer in answers] == [
        (401, "unauthenticated")
    ] * 3
