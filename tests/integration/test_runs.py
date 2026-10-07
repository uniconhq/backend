"""The three doors a grading run calls, over HTTP with no session and no
Origin: the CI's question about a run answered when its signature checks
over the bytes as they were sent and refused when it does not or its body
was changed; the envelope served for its key and not without it; and the
run's reports taken under its token, a finished one leaving the result the
contestant then reads as the task's test groups show it, its numbers as
they were written, and the organisers read whole; and the run's log, read
by an observer of the task as plain text that runs nothing, and never by
its contestant. A wrong or missing token, a body that is no report, a
body past the bound, and a report or an envelope fetch for a grading that
is over are each refused with their code.
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

from tests.integration.conftest import ORIGIN, SUM, TASK, edit_task, sign_in_as, upload

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
            "inputs": {
                "submission": {"uploads": [made["id"]]},
                "language": {"value": "python"},
            },
        },
        headers=ORIGIN,
    )
    grading: str = submitted.json()["grading"]["id"]
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
    content = body if isinstance(body, bytes) else json.dumps(body).encode()
    return await client.post(
        callback, content=content, headers={"Authorization": f"Bearer {given}"}
    )


REPORT = (
    b'{"event": "finished", "result": {"schema_version": 5, "stopped": null, '
    b'"stopped_by": null, "tests": [{"test": "main/1", "outcome": "accepted", '
    b'"values": {"time_ms": 12.5, "memory_kb": 2048}}], '
    b'"values": {"log": ""}, "run_log": %s, "error": null}}'
)
"""A finished report as the harness writes it, a number with a point in it
included, with the run log's URL put in."""
ROW = {"test": "main/1", "outcome": "accepted", "values": {"time_ms": 12.5, "memory_kb": 2048}}


def _finished(log: str | None) -> bytes:
    return REPORT % json.dumps(log).encode()


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
    assert (envelope["schema_version"], envelope["grading_id"]) == (5, started.grading)
    assert envelope["secrets"] == {}
    assert envelope["callback"]["token"]
    for refused in (wrong, keyless):
        assert (refused.status_code, refused.json()["code"]) == (404, "not_found")
    submission = await client.get(f"{TASK}/submissions/1")
    assert submission.json()["grading"]["status"] == "running"


async def test_a_finished_report_leaves_the_result_the_contestant_reads(
    client: httpx.AsyncClient, entered: FakeForge, held_setup: Setup
) -> None:
    started = await _started(client, entered, held_setup)
    envelope = await _envelope(client, started)
    entered.objects.put(envelope["log_put"], LOG)

    began = await _report(client, envelope, {"event": "started"})
    moved = await _report(
        client, envelope, {"event": "progress", "step": "run", "done": 1, "total": 1}
    )
    report = _finished(urlsplit(envelope["log_put"])._replace(query="").geturl())
    finished = await _report(client, envelope, report)
    again = await _report(client, envelope, report)
    detail = await client.get(f"{TASK}/submissions/1")
    run_log = await client.get(f"{TASK}/submissions/1/log")

    assert [began.json(), moved.json()] == [{"status": "running"}] * 2
    assert finished.json() == again.json() == {"status": "done"}
    grading = detail.json()["grading"]
    assert (grading["status"], grading["stopped"], grading["outcome"]) == (
        "done",
        None,
        "accepted",
    )
    assert grading["groups"] == [
        {
            "group": "main",
            "show": "always",
            "outcome": "accepted",
            "tests": [ROW],
            "shown_at": None,
            "ran": True,
        }
    ]
    assert grading["values"] == {"log": ""}
    assert b'"time_ms":12.5' in detail.content
    assert (run_log.status_code, run_log.json()["code"]) == (404, "not_found")


async def test_the_organisers_read_the_result_whole_with_its_log(
    client: httpx.AsyncClient, entered: FakeForge, held_setup: Setup
) -> None:
    await _finished_with_log(client, entered, held_setup)
    await sign_in_as(client, entered, 7)

    [grading] = (await client.get(f"{TASK}/gradings")).json()

    assert (grading["status"], grading["log"]) == ("done", True)
    assert grading["result"] == {
        "stopped": None,
        "tests": [ROW],
        "values": {"log": ""},
        "error": None,
    }


async def test_an_observer_reads_a_gradings_log_as_plain_text_that_runs_nothing(
    client: httpx.AsyncClient, entered: FakeForge, held_setup: Setup
) -> None:
    grading = await _finished_with_log(client, entered, held_setup)
    await sign_in_as(client, entered, 7)

    run_log = await client.get(f"{TASK}/gradings/{grading}/log")

    assert run_log.status_code == 200, run_log.text
    assert run_log.content == LOG
    assert run_log.headers["content-type"] == "text/plain; charset=utf-8"
    assert run_log.headers["x-content-type-options"] == "nosniff"
    assert run_log.headers["content-security-policy"] == "default-src 'none'; sandbox"
    assert run_log.headers["cache-control"] == "private, no-store"


async def test_a_log_larger_than_is_read_back_is_refused_with_the_limit(
    client: httpx.AsyncClient, entered: FakeForge, held_setup: Setup
) -> None:
    grading = await _finished_with_log(client, entered, held_setup, b"x" * (9 * MIB + 1))
    await sign_in_as(client, entered, 7)

    refused = await client.get(f"{TASK}/gradings/{grading}/log")

    assert (refused.status_code, refused.json()["code"]) == (409, "log_too_large")
    assert refused.json()["limit"] == 9 * MIB


async def test_a_grading_whose_run_wrote_no_log_has_none_to_read(
    client: httpx.AsyncClient, entered: FakeForge, held_setup: Setup
) -> None:
    started = await _started(client, entered, held_setup)
    envelope = await _envelope(client, started)
    finished = await _report(client, envelope, _finished(None))
    await sign_in_as(client, entered, 7)

    missing = await client.get(f"{TASK}/gradings/{started.grading}/log")

    assert finished.json() == {"status": "done"}, finished.text
    assert (missing.status_code, missing.json()["code"]) == (404, "not_found")


async def _finished_with_log(
    client: httpx.AsyncClient, forge: FakeForge, setup: Setup, log: bytes = LOG
) -> str:
    """carol's first submission graded, its run's log written; its grading's
    id.
    """
    started = await _started(client, forge, setup)
    envelope = await _envelope(client, started)
    forge.objects.put(envelope["log_put"], log)
    report = _finished(urlsplit(envelope["log_put"])._replace(query="").geturl())
    finished = await _report(client, envelope, report)
    assert finished.json() == {"status": "done"}, finished.text
    return started.grading


@pytest.mark.parametrize(
    ("show", "outcome"),
    [("verdict", "accepted"), ("after_close", None)],
)
async def test_a_group_that_shows_less_answers_with_less_until_the_reveal(
    client: httpx.AsyncClient,
    entered: FakeForge,
    held_setup: Setup,
    show: str,
    outcome: str | None,
) -> None:
    await sign_in_as(client, entered, 7)
    await edit_task(client, "main: {each: 100}", f"main: {{pass: 100, show: {show}}}")
    await sign_in_as(client, entered, 20)
    await _finished_with_log(client, entered, held_setup)

    detail = await client.get(f"{TASK}/submissions/1")
    listed = await client.get(f"{TASK}/submissions")

    grading = detail.json()["grading"]
    assert (grading["status"], grading["outcome"]) == ("done", outcome)
    assert grading["groups"] == [
        {
            "group": "main",
            "show": show,
            "outcome": outcome,
            "tests": None,
            "shown_at": "2026-09-26T15:00:00Z",
            "ran": True,
        }
    ]
    assert listed.json() == [detail.json()]


async def test_a_run_that_failed_on_the_platforms_side_is_still_being_graded_to_its_contestant(
    client: httpx.AsyncClient, entered: FakeForge, held_setup: Setup
) -> None:
    started = await _started(client, entered, held_setup)
    envelope = await _envelope(client, started)
    failed = {
        "schema_version": 5,
        "stopped": "system_error",
        "stopped_by": None,
        "tests": [{"test": "main/1", "outcome": "skipped", "values": {}}],
        "values": {},
        "run_log": None,
        "error": "The run step's container did not start.",
    }

    finished = await _report(client, envelope, {"event": "finished", "result": failed})
    detail = await client.get(f"{TASK}/submissions/1")
    await sign_in_as(client, entered, 7)
    [row] = (await client.get(f"{TASK}/gradings")).json()

    assert finished.json() == {"status": "system_error"}
    assert detail.json()["grading"]["status"] == "running"
    assert (detail.json()["grading"]["stopped"], detail.json()["grading"]["groups"]) == (None, [])
    assert (row["status"], row["error"]) == ("system_error", failed["error"])
    assert row["result"]["stopped"] == "system_error"


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
    await _report(client, envelope, _finished(None))

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
