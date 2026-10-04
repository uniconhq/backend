"""The three doors a grading run calls, over HTTP with no session and no
Origin: the CI's question about a run answered when its signature checks
over the bytes as they were sent and refused when it does not or its body
was changed; the envelope served for its key and not without it; and the
run's reports taken under its token, a finished one leaving the verdict the
contestant then reads as the stage shows it, with the run's log. A wrong or
missing token, a body that is no report, a body past the bound, and a report
or an envelope fetch for a grading that is over are each refused with their
code.
"""

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

import httpx
import pytest
from forge.api import tasks
from forge.api.runs import CI_CONFIG_PATH, CiRequest
from forge.testing import FakeClock, FakeForge, Setup

from tests.integration.conftest import ORIGIN, SUM, TASK, edit_task, enter, sign_in_as, upload

SOURCE = b"print(sum(map(int, input().split())))\n"
LOG = b"compile: ok\nrun 1: accepted\n"
MIB = 1024 * 1024


@dataclass(frozen=True)
class Started:
    """A run the fake CI started for carol's first submission: the grading's
    id and the variables the run was started with.
    """

    grading: str
    variables: Mapping[str, str]

    @property
    def envelope(self) -> str:
        """The envelope's URL as the run is given it, path and query."""
        parts = urlsplit(self.variables["UNICON_ENVELOPE_URL"])
        return f"{parts.path}?{parts.query}"


async def _submitted(client: httpx.AsyncClient, forge: FakeForge) -> str:
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


async def _started(client: httpx.AsyncClient, forge: FakeForge, setup: Setup) -> Started:
    grading = await _submitted(client, forge)
    [run] = forge.state.runs.values()
    assert run.variables["UNICON_GRADING_ID"] == grading
    return Started(grading, run.variables)


async def _asked(
    client: httpx.AsyncClient,
    forge: FakeForge,
    clock: FakeClock,
    monkeypatch: pytest.MonkeyPatch,
    **options: Any,
) -> tuple[CiRequest, httpx.Response]:
    """carol's first submission, whose start the fake CI answers by asking
    the platform what the run is, as the real CI does while the start is
    under way; the question it asked and the answer it was given.
    """
    asked: list[tuple[CiRequest, httpx.Response]] = []
    start = forge.grading.start_run

    async def asking(as_: Any, run: Any) -> Any:
        variables = dict(forge.grading.run_variables(run))
        request = forge.grading.config_request(
            tasks.task_id_of(SUM), variables, now=clock.now(), **options
        )
        answer = await client.post(request.target, content=request.body, headers=request.headers)
        asked.append((request, answer))
        return await start(as_, run)

    monkeypatch.setattr(forge.grading, "start_run", asking)
    await _submitted(client, forge)
    [found] = asked
    return found


async def _envelope(client: httpx.AsyncClient, started: Started) -> dict[str, Any]:
    fetched = await client.get(started.envelope)
    assert fetched.status_code == 200, fetched.text
    body: dict[str, Any] = fetched.json()
    return body


async def _report(
    client: httpx.AsyncClient, envelope: dict[str, Any], body: object, token: str | None = None
) -> httpx.Response:
    callback = urlsplit(envelope["callback"]["url"]).path
    given = envelope["callback"]["token"] if token is None else token
    return await client.post(
        callback, content=json.dumps(body).encode(), headers={"Authorization": f"Bearer {given}"}
    )


def _verdict(log: str | None) -> dict[str, Any]:
    return {
        "schema_version": 4,
        "outcome": "accepted",
        "metrics": {"score": 100},
        "tests": [
            {"id": "1", "outcome": "accepted", "time_ms": 12, "memory_kb": 2048, "metrics": {}}
        ],
        "summary": "Every test passed.",
        "log": log,
    }


async def test_the_cis_signed_question_is_answered_without_an_origin(
    client: httpx.AsyncClient,
    entered: FakeForge,
    clock: FakeClock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request, answered = await _asked(client, entered, clock, monkeypatch)

    assert request.target == CI_CONFIG_PATH
    assert answered.status_code == 200, answered.text
    assert answered.headers["content-type"] == "application/json"
    assert answered.headers["cache-control"] == "no-store"
    assert json.loads(answered.content)["steps"][0]["name"] == "grade"


@pytest.mark.parametrize("change", ["body", "key"])
async def test_a_question_the_ci_did_not_sign_is_refused(
    client: httpx.AsyncClient,
    entered: FakeForge,
    clock: FakeClock,
    monkeypatch: pytest.MonkeyPatch,
    change: str,
) -> None:
    options: dict[str, Any] = {"body": b'{"task": "acme/spring/sum"}'}
    if change == "key":
        options = {"key": b"another key"}

    _, refused = await _asked(client, entered, clock, monkeypatch, **options)

    assert (refused.status_code, refused.json()["code"]) == (403, "ci_request_refused")
    assert refused.json()["detail"] == "The platform does not answer this request."


async def test_a_question_past_the_bound_is_refused_before_it_is_read(
    client: httpx.AsyncClient, entered: FakeForge
) -> None:
    refused = await client.post(CI_CONFIG_PATH, content=b"x" * (MIB + 1))

    assert (refused.status_code, refused.json()["code"]) == (413, "payload_too_large")


async def test_the_envelope_is_served_for_its_key_and_not_without_it(
    client: httpx.AsyncClient, entered: FakeForge, held_setup: Setup
) -> None:
    started = await _started(client, entered, held_setup)
    path = urlsplit(started.envelope).path

    fetched = await client.get(started.envelope)
    wrong = await client.get(f"{path}?key=wrong")
    keyless = await client.get(path)

    assert fetched.status_code == 200, fetched.text
    assert fetched.headers["cache-control"] == "no-store"
    envelope = fetched.json()
    assert (envelope["schema_version"], envelope["grading_id"]) == (4, started.grading)
    assert envelope["callback"]["token"]
    for refused in (wrong, keyless):
        assert (refused.status_code, refused.json()["code"]) == (404, "not_found")
    submission = await client.get(f"{TASK}/submissions/1")
    assert submission.json()["gradings"][0]["status"] == "running"


async def test_a_finished_report_leaves_the_verdict_the_contestant_reads(
    client: httpx.AsyncClient, entered: FakeForge, held_setup: Setup
) -> None:
    started = await _started(client, entered, held_setup)
    envelope = await _envelope(client, started)
    entered.objects.put(envelope["log_put"], LOG)

    began = await _report(client, envelope, {"event": "started"})
    moved = await _report(
        client, envelope, {"event": "progress", "step": "run", "done": 1, "total": 1}
    )
    verdict = _verdict(log=urlsplit(envelope["log_put"])._replace(query="").geturl())
    finished = await _report(client, envelope, {"event": "finished", "verdict": verdict})
    again = await _report(client, envelope, {"event": "finished", "verdict": verdict})
    detail = await client.get(f"{TASK}/submissions/1")
    run_log = await client.get(f"{TASK}/submissions/1/log")

    assert [began.json(), moved.json()] == [{"status": "running"}] * 2
    assert finished.json() == again.json() == {"status": "done"}
    [grading] = detail.json()["gradings"]
    assert (grading["status"], grading["outcome"], grading["metrics"]) == (
        "done",
        "accepted",
        {"score": 100},
    )
    assert (grading["summary"], grading["log"]) == ("Every test passed.", True)
    assert grading["tests"] == [{**row, "message": None} for row in verdict["tests"]]
    assert run_log.status_code == 200, run_log.text
    assert run_log.content == LOG
    assert run_log.headers["content-type"] == "text/plain; charset=utf-8"
    assert run_log.headers["x-content-type-options"] == "nosniff"


async def _finished_with_log(
    client: httpx.AsyncClient, forge: FakeForge, setup: Setup
) -> dict[str, Any]:
    """carol's first submission graded, its run's log written; the verdict."""
    started = await _started(client, forge, setup)
    envelope = await _envelope(client, started)
    forge.objects.put(envelope["log_put"], LOG)
    verdict = _verdict(log=urlsplit(envelope["log_put"])._replace(query="").geturl())
    finished = await _report(client, envelope, {"event": "finished", "verdict": verdict})
    assert finished.json() == {"status": "done"}, finished.text
    return verdict


@pytest.mark.parametrize(
    ("show", "shown"),
    [
        (
            "metrics",
            {"outcome": "accepted", "metrics": {"score": 100}, "summary": None, "tests": None},
        ),
        ("hidden", {"outcome": None, "metrics": None, "summary": None, "tests": None}),
    ],
)
async def test_a_stage_that_shows_less_answers_with_less_and_no_log(
    client: httpx.AsyncClient,
    entered: FakeForge,
    held_setup: Setup,
    show: str,
    shown: dict[str, Any],
) -> None:
    await sign_in_as(client, entered, 7)
    stages = f"\nstages:\n  - id: default\n    show: {show}\n\nlimits:"
    await edit_task(client, "\nlimits:", stages)
    await sign_in_as(client, entered, 20)
    await _finished_with_log(client, entered, held_setup)

    detail = await client.get(f"{TASK}/submissions/1")
    listed = await client.get(f"{TASK}/submissions")
    run_log = await client.get(f"{TASK}/submissions/1/log")

    [grading] = detail.json()["gradings"]
    assert (grading["status"], grading["show"], grading["log"]) == ("done", show, False)
    assert {name: grading[name] for name in shown} == shown
    assert listed.json() == [detail.json()]
    assert (run_log.status_code, run_log.json()["code"]) == (404, "not_found")


async def test_another_contestants_log_is_no_such_log(
    client: httpx.AsyncClient, entered: FakeForge, held_setup: Setup
) -> None:
    await _finished_with_log(client, entered, held_setup)
    await enter(client, entered, held_setup, 8)

    refused = await client.get(f"{TASK}/submissions/1/log")
    await sign_in_as(client, entered, 20)
    own = await client.get(f"{TASK}/submissions/1/log")

    assert (refused.status_code, refused.json()["code"]) == (404, "not_found")
    assert (own.status_code, own.content) == (200, LOG)


async def test_a_submission_with_no_log_has_none_to_read(
    client: httpx.AsyncClient, entered: FakeForge
) -> None:
    await _submitted(client, entered)

    missing = await client.get(f"{TASK}/submissions/1/log")
    other_stage = await client.get(f"{TASK}/submissions/1/log", params={"stage": "hidden"})

    for refused in (missing, other_stage):
        assert (refused.status_code, refused.json()["code"]) == (404, "not_found")


@pytest.mark.parametrize(
    ("authorization", "body", "status", "code"),
    [
        ("Bearer wrong", {"event": "started"}, 401, "invalid_token"),
        (None, {"event": "started"}, 401, "invalid_token"),
        ("Basic abc", {"event": "started"}, 401, "invalid_token"),
        ("", {"event": "restarted"}, 422, "invalid_callback"),
        ("", {"event": "progress", "step": "run"}, 422, "invalid_callback"),
    ],
    ids=["wrong token", "no token", "another scheme", "no such event", "no counts"],
)
async def test_a_report_that_is_not_the_runs_is_refused_with_its_code(
    client: httpx.AsyncClient,
    entered: FakeForge,
    held_setup: Setup,
    authorization: str | None,
    body: object,
    status: int,
    code: str,
) -> None:
    started = await _started(client, entered, held_setup)
    envelope = await _envelope(client, started)
    headers = {} if authorization is None else {"Authorization": authorization}
    if authorization == "":
        headers = {"Authorization": f"Bearer {envelope['callback']['token']}"}
    callback = urlsplit(envelope["callback"]["url"]).path

    refused = await client.post(callback, content=json.dumps(body).encode(), headers=headers)

    assert (refused.status_code, refused.json()["code"]) == (status, code)


async def test_a_grading_that_takes_no_reports_is_closed(
    client: httpx.AsyncClient, entered: FakeForge, held_setup: Setup
) -> None:
    started = await _started(client, entered, held_setup)
    envelope = await _envelope(client, started)
    await _report(client, envelope, {"event": "finished", "verdict": _verdict(log=None)})

    late = await _report(client, envelope, {"event": "started"})
    fetched_late = await client.get(started.envelope)

    for refused in (late, fetched_late):
        assert (refused.status_code, refused.json()["code"]) == (410, "grading_closed")


async def test_a_report_past_the_bound_is_refused_before_it_is_read(
    client: httpx.AsyncClient, entered: FakeForge, held_setup: Setup
) -> None:
    started = await _started(client, entered, held_setup)
    envelope = await _envelope(client, started)
    callback = urlsplit(envelope["callback"]["url"]).path

    refused = await client.post(
        callback,
        content=b"x" * (4 * MIB + 1),
        headers={"Authorization": f"Bearer {envelope['callback']['token']}"},
    )

    assert (refused.status_code, refused.json()["code"]) == (413, "payload_too_large")
