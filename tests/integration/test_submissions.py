"""A contestant's submissions through the routes: a submit answered with the
new submission and its queued grading, the same one read back in the list
and by its number, what it was made with and one of its files as a download
nothing in the browser runs; the same key sent twice making one submission;
and the refusals a submit meets, each with its code and what it carries: the
task's rate with `retry_at` and a `Retry-After` header, the submissions the
task allows, a key that is not one, and an upload that is not a checked file
or not the caller's. Another contestant's submission is no such submission,
and every route needs a session.
"""

import hashlib
import uuid
from datetime import timedelta
from typing import Any

import httpx
from forge.testing import FakeClock, FakeForge, Setup

from tests.integration.conftest import (
    ORIGIN,
    TASK,
    edit_task,
    enter,
    sign_in_as,
    upload,
)

SOURCE = b"print(sum(map(int, input().split())))\n"
KEY = "key-0001-aaaa"
SUBMISSIONS = f"{TASK}/submissions"
MAIN = "files/submission/main.py"


def _submit_body(*uploads: str, key: str = KEY) -> dict[str, Any]:
    return {
        "idempotency_key": key,
        "inputs": {"submission": {"uploads": list(uploads), "language": "python"}},
    }


async def _submit(
    client: httpx.AsyncClient, forge: FakeForge, key: str = KEY, content: bytes = SOURCE
) -> httpx.Response:
    made = await upload(client, forge, content)
    return await client.post(SUBMISSIONS, json=_submit_body(made["id"], key=key), headers=ORIGIN)


async def test_a_submit_answers_with_its_queued_grading_and_reads_back(
    client: httpx.AsyncClient, entered: FakeForge
) -> None:
    submitted = await _submit(client, entered)
    listed = await client.get(SUBMISSIONS)
    one = await client.get(f"{SUBMISSIONS}/1")

    assert submitted.status_code == 201, submitted.text
    body = submitted.json()
    assert (body["number"], body["submitted_at"]) == (1, "2026-09-26T12:00:00Z")
    [grading] = body["gradings"]
    uuid.UUID(grading.pop("id"))
    assert grading == {
        "stage": "default",
        "attempt": 1,
        "status": "queued",
        "show": "full",
        "outcome": None,
        "metrics": None,
        "summary": None,
        "tests": None,
        "log": False,
    }
    first = submitted.json()["gradings"][0]
    started = {**submitted.json(), "gradings": [{**first, "status": "dispatched"}]}
    assert listed.json() == [started]
    assert one.json() == started


async def test_a_submission_gives_back_what_it_was_made_with(
    client: httpx.AsyncClient, entered: FakeForge
) -> None:
    await _submit(client, entered)

    files = await client.get(f"{SUBMISSIONS}/1/files")
    source = await client.get(f"{SUBMISSIONS}/1/files/{MAIN}")
    absent = await client.get(f"{SUBMISSIONS}/1/files/files/submission/other.py")
    document = await client.get(f"{SUBMISSIONS}/1/files/submission.json")

    assert files.json() == {
        "number": 1,
        "inputs": {"submission": {"files": [MAIN], "language": "python", "value": None}},
    }
    assert source.status_code == 200
    assert source.content == SOURCE
    assert source.headers["content-type"] == "application/octet-stream"
    assert source.headers["content-disposition"] == 'attachment; filename="main.py"'
    assert source.headers["x-content-type-options"] == "nosniff"
    assert "sandbox" in source.headers["content-security-policy"]
    assert (absent.status_code, absent.json()["code"]) == (404, "not_found")
    assert (document.status_code, document.json()["code"]) == (404, "not_found")


async def test_the_same_key_sent_twice_makes_one_submission(
    client: httpx.AsyncClient, entered: FakeForge
) -> None:
    first = await _submit(client, entered)
    again = await _submit(client, entered)

    assert again.status_code == 201, again.text
    assert again.json()["number"] == first.json()["number"]
    assert [grading["id"] for grading in again.json()["gradings"]] == [
        grading["id"] for grading in first.json()["gradings"]
    ]
    assert len((await client.get(SUBMISSIONS)).json()) == 1


async def test_a_submit_inside_the_tasks_rate_is_refused_until_it_says(
    client: httpx.AsyncClient, entered: FakeForge, clock: FakeClock
) -> None:
    await _submit(client, entered)

    refused = await _submit(client, entered, key="key-0002-bbbb")
    clock.advance(timedelta(seconds=30))
    later = await _submit(client, entered, key="key-0003-cccc")

    assert (refused.status_code, refused.json()["code"]) == (429, "rate_limited")
    assert refused.json()["rate"] == "1 per 30s"
    assert refused.json()["retry_at"] == "2026-09-26T12:00:30+00:00"
    assert refused.headers["retry-after"] == "Sat, 26 Sep 2026 12:00:30 GMT"
    assert (later.status_code, later.json()["number"]) == (201, 2)


async def test_a_submit_past_the_tasks_submissions_is_refused_with_the_limit(
    client: httpx.AsyncClient, entered: FakeForge, clock: FakeClock
) -> None:
    await sign_in_as(client, entered, 7)
    await edit_task(client, "submissions: 50", "submissions: 1")
    await sign_in_as(client, entered, 20)
    await _submit(client, entered)
    clock.advance(timedelta(minutes=1))

    refused = await _submit(client, entered, key="key-0002-bbbb")

    assert (refused.status_code, refused.json()["code"]) == (409, "submission_limit")
    assert refused.json()["limit"] == 1


async def test_a_submit_with_a_key_that_is_not_one_is_refused(
    client: httpx.AsyncClient, entered: FakeForge
) -> None:
    refused = await _submit(client, entered, key="short")

    assert (refused.status_code, refused.json()["code"]) == (422, "invalid_idempotency_key")


async def test_an_upload_that_is_not_checked_is_not_ready(
    client: httpx.AsyncClient, entered: FakeForge
) -> None:
    slot = await client.post(
        f"{TASK}/uploads",
        json={
            "input": "submission",
            "filename": "main.py",
            "size": len(SOURCE),
            "sha256": hashlib.sha256(SOURCE).hexdigest(),
        },
        headers=ORIGIN,
    )
    upload_id = slot.json()["id"]

    refused = await client.post(SUBMISSIONS, json=_submit_body(upload_id), headers=ORIGIN)

    assert (refused.status_code, refused.json()["code"]) == (409, "upload_not_ready")
    assert refused.json()["uploads"] == [upload_id]


async def test_inputs_that_do_not_fit_the_task_are_refused_at_their_input(
    client: httpx.AsyncClient, entered: FakeForge
) -> None:
    made = await upload(client, entered, SOURCE)
    body = _submit_body(made["id"])
    body["inputs"]["submission"]["language"] = "cobol"

    refused = await client.post(SUBMISSIONS, json=body, headers=ORIGIN)

    assert (refused.status_code, refused.json()["code"]) == (422, "invalid_inputs")
    assert refused.json()["errors"][0]["input"] == "submission"


async def test_another_contestants_submission_is_no_such_submission(
    client: httpx.AsyncClient, entered: FakeForge, held_setup: Setup
) -> None:
    carols = await upload(client, entered, SOURCE)
    await client.post(SUBMISSIONS, json=_submit_body(carols["id"]), headers=ORIGIN)
    await enter(client, entered, held_setup, 8)

    answers = [
        await client.get(f"{SUBMISSIONS}/1"),
        await client.get(f"{SUBMISSIONS}/1/files"),
        await client.get(f"{SUBMISSIONS}/1/files/{MAIN}"),
    ]
    listed = await client.get(SUBMISSIONS)
    taken = await client.post(
        SUBMISSIONS, json=_submit_body(carols["id"], key="key-0002-bbbb"), headers=ORIGIN
    )

    assert [(answer.status_code, answer.json()["code"]) for answer in answers] == [
        (404, "not_found")
    ] * 3
    assert listed.json() == []
    assert (taken.status_code, taken.json()["code"]) == (404, "upload_not_yours")
    assert taken.json()["uploads"] == [carols["id"]]


async def test_a_number_that_cannot_be_a_submission_is_refused_before_forge(
    client: httpx.AsyncClient, entered: FakeForge
) -> None:
    for number in ("0", str(2**31), "one"):
        answer = await client.get(f"{SUBMISSIONS}/{number}")
        assert (answer.status_code, answer.json()["code"]) == (422, "validation_error"), number


async def test_the_submission_routes_need_a_session(
    client: httpx.AsyncClient, entered: FakeForge
) -> None:
    await _submit(client, entered)
    client.cookies.clear()

    answers = [
        await client.post(SUBMISSIONS, json=_submit_body(), headers=ORIGIN),
        await client.get(SUBMISSIONS),
        await client.get(f"{SUBMISSIONS}/1"),
        await client.get(f"{SUBMISSIONS}/1/files"),
        await client.get(f"{SUBMISSIONS}/1/files/{MAIN}"),
    ]

    assert [(answer.status_code, answer.json()["code"]) for answer in answers] == [
        (401, "unauthenticated")
    ] * 5
