"""The doors a grading's pipeline calls, over HTTP with no session and no
Origin: the CI's question about a pipeline answered when its signature
checks over the bytes as they were sent and refused when it does not or
its body was changed; and a step's door, which takes the step's token at
each of its five routes, handing forge the header and the body as they
arrived, answers a step left with nothing to do 204, keeps each body to its
bound, and never logs the token. A submission's pipeline run through those
doors step by step leaves the result its contestant then reads, with its
runs and the values its scoring shows, the organisers read whole, the
task's form then saying it has a graded submission. A run that failed on
the platform's side is delayed to its contestant and a system error to the
organisers.
"""

import hashlib
import json
import logging
import uuid
from typing import Any
from urllib.parse import urlsplit

import httpx
import pytest
from forge.api import runs
from forge.api.runs import CI_CONFIG_PATH, GradingStatus, InboundRequest
from forge.testing import FakeClock, FakeForge, OrgId, Setup

from tests.integration.conftest import MACHINES, ORIGIN, TASK, run_pipelines, sign_in_as, upload

SOURCE = b"print(sum(map(int, input().split())))\n"
MIB = 1024 * 1024


async def _submitted(client: httpx.AsyncClient, forge: FakeForge) -> str:
    """carol's first submission of acme/spring/sum; its grading's id."""
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
    assert submitted.status_code == 201, submitted.text
    grading: str = submitted.json()["grading"]["id"]
    return grading


async def _asked(
    client: httpx.AsyncClient,
    forge: FakeForge,
    clock: FakeClock,
    monkeypatch: pytest.MonkeyPatch,
    **options: Any,
) -> tuple[InboundRequest, httpx.Response]:
    """carol's first submission, whose start the fake CI answers by asking
    the platform what the pipeline is, as the real CI does while the start
    is under way; the question it asked and the answer it was given.
    """
    asked: list[tuple[InboundRequest, httpx.Response]] = []
    start = forge.grading.start_pipeline

    async def asking(as_: Any, run: Any) -> Any:
        made = await start(as_, run)
        found = forge.ci.runs[made]
        request = forge.grading.config_request(
            OrgId(found.task.split("/", 1)[0]), found.variables, now=clock.now(), **options
        )
        answer = await client.post(request.target, content=request.body, headers=request.headers)
        asked.append((request, answer))
        return made

    monkeypatch.setattr(forge.grading, "start_pipeline", asking)
    await _submitted(client, forge)
    [found] = asked
    return found


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
    steps = json.loads(answered.content)["steps"]
    assert [step["name"] for step in steps][-1] == "report"
    assert all(step["settings"]["data_token"] for step in steps)


@pytest.mark.parametrize("change", ["body", "key"])
async def test_a_question_the_ci_did_not_sign_is_refused(
    client: httpx.AsyncClient,
    entered: FakeForge,
    clock: FakeClock,
    monkeypatch: pytest.MonkeyPatch,
    change: str,
) -> None:
    options: dict[str, Any] = {"body": b'{"org": "acme"}'}
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


async def test_a_pipeline_run_step_by_step_leaves_the_result_the_contestant_reads(
    client: httpx.AsyncClient, entered: FakeForge
) -> None:
    grading = await _submitted(client, entered)

    await run_pipelines(client)
    detail = await client.get(f"{TASK}/submissions/1")
    listed = await client.get(f"{TASK}/submissions")

    result = detail.json()["grading"]
    assert (result["id"], result["status"], result["compiled"]) == (grading, "graded", 1)
    [run] = result["runs"]
    assert (run["group"], run["place"], run["id"]) == ("all", 1, None)
    assert (run["verdict"], run["passed"]) == ("accepted", 1)
    assert run["reports"] == {"score": "1", "time_ms": "12", "memory_kb": "2048"}
    [score] = result["run_values"]
    assert (score["name"], score["number"], score["waiting"]) == ("score", "1", False)
    assert listed.json() == [detail.json()]


async def test_the_organisers_read_the_result_whole(
    client: httpx.AsyncClient, entered: FakeForge
) -> None:
    grading = await _submitted(client, entered)
    await sign_in_as(client, entered, 7)
    before = (await client.get(f"{TASK}/workflow-form")).json()
    await sign_in_as(client, entered, 20)
    await run_pipelines(client)
    await sign_in_as(client, entered, 7)

    [entry] = (await client.get(f"{TASK}/gradings")).json()
    form = (await client.get(f"{TASK}/workflow-form")).json()

    row = entry["grading"]
    assert (row["id"], row["status"], row["latest"]) == (grading, "done", True)
    assert row["pipeline"] == "early"
    assert "log" not in row and "progress" not in row
    by = entry["by"]
    assert (by["entrant_name"], by["user_id"], by["username"]) == ("carol", 20, "carol")
    assert (before["graded"], form["graded"]) == (False, True)
    result = row["result"]
    assert (result["schema_version"], result["error"]) == (6, None)
    [run] = result["runs"]
    assert (run["id"], run["verdict"], run["passed"]) == ("r1", "accepted", 1)


async def test_a_run_that_failed_on_the_platforms_side_is_delayed_to_its_contestant(
    client: httpx.AsyncClient, entered: FakeForge
) -> None:
    await _submitted(client, entered)

    await _faulted(client)
    detail = await client.get(f"{TASK}/submissions/1")
    await sign_in_as(client, entered, 7)
    [entry] = (await client.get(f"{TASK}/gradings")).json()

    assert detail.json()["grading"]["status"] == "delayed"
    row = entry["grading"]
    assert (row["status"], row["result"]["runs"][0]["verdict"]) == ("system_error", "system_error")
    assert row["error"]


async def _faulted(client: httpx.AsyncClient) -> None:
    """The pipeline started last run with its first step writing an
    `outputs.json` that is not JSON, a fault of the platform's side, and
    then its report.
    """
    _, steps = MACHINES[client].started.pop()
    first, report = steps[0]["settings"], steps[-1]["settings"]
    door = urlsplit(first["data_url"]).path
    headers = {"Authorization": f"Bearer {first['data_token']}"}
    assert (await client.get(door, headers=headers)).status_code == 200
    written = b"not json"
    listed = {"path": "outputs.json", "sha256": hashlib.sha256(written).hexdigest(), "size": 8}
    links = await client.post(
        f"{door}/uploads", content=json.dumps({"files": [listed]}).encode(), headers=headers
    )
    MACHINES[client].forge.objects.put(links.json()["files"]["outputs.json"], written)
    assert (await client.post(f"{door}/done", content=b"{}", headers=headers)).status_code == 204
    reported = await client.post(
        urlsplit(report["data_url"]).path,
        content=b"{}",
        headers={"Authorization": f"Bearer {report['data_token']}"},
    )
    assert reported.status_code == 200, reported.text


# A step's door


STEP_TOKEN = "step-token-81c4d2"
SHA256 = "0" * 64


def _step_door(grading: str, step: str = "compile") -> str:
    return runs.STEP_PATH.format(grading=grading, step=step)


async def test_a_steps_door_takes_only_a_steps_token_and_never_logs_it(
    client: httpx.AsyncClient,
    entered: FakeForge,
    held_setup: Setup,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    grading = await _submitted(client, entered)
    door = _step_door(grading)
    headers = {"Authorization": f"Bearer {STEP_TOKEN}"}

    answers = [
        await client.get(door, headers=headers),
        await client.post(_step_door(grading, "report"), content=b"{}", headers=headers),
        await client.post(f"{door}/uploads", content=b'{"files": []}', headers=headers),
        await client.post(f"{door}/done", content=b"{}", headers=headers),
        await client.get(f"{door}/files/{SHA256}", headers=headers),
    ]

    assert [(a.status_code, a.json()["code"]) for a in answers] == [(401, "invalid_token")] * 5
    assert STEP_TOKEN not in caplog.text


async def test_a_steps_door_hands_forge_what_arrived_and_answers_in_kind(
    client: httpx.AsyncClient, held_setup: Setup, monkeypatch: pytest.MonkeyPatch
) -> None:
    grading = uuid.uuid4()
    door = _step_door(str(grading))
    headers = {"Authorization": f"Bearer {STEP_TOKEN}"}
    handed: list[tuple[Any, ...]] = []
    job: list[bytes | None] = [b'{"schema_version": 1}']

    async def step_job(*given: Any) -> bytes | None:
        handed.append(("job", *given))
        return job[0]

    async def step_report(*given: Any) -> GradingStatus:
        handed.append(("report", *given))
        return GradingStatus.DONE

    async def step_admits(*given: Any) -> None:
        handed.append(("admits", *given))

    async def step_uploads(*given: Any) -> dict[str, Any]:
        handed.append(("uploads", *given))
        return {"files": {"outputs.json": "http://store.test/put"}}

    async def step_done(*given: Any) -> None:
        handed.append(("done", *given))

    async def step_file(*given: Any) -> bytes:
        handed.append(("file", *given))
        return b"\x00\x01"

    for action in (step_job, step_report, step_admits, step_uploads, step_done, step_file):
        monkeypatch.setattr(runs, action.__name__, action)

    served = await client.get(door, headers=headers)
    job[0] = None
    nothing = await client.get(door, headers=headers)
    reported = await client.post(door, content=b"{}", headers=headers)
    links = await client.post(f"{door}/uploads", content=b'{"files": []}', headers=headers)
    done = await client.post(f"{door}/done", content=b"{}", headers=headers)
    file = await client.get(f"{door}/files/{SHA256}", headers=headers)

    assert (served.status_code, served.content) == (200, b'{"schema_version": 1}')
    assert served.headers["content-type"] == "application/json"
    assert (nothing.status_code, nothing.content) == (204, b"")
    assert (reported.status_code, reported.json()) == (200, {"status": "done"})
    assert links.json() == {"files": {"outputs.json": "http://store.test/put"}}
    assert (done.status_code, done.content) == (204, b"")
    assert (file.content, file.headers["content-type"]) == (b"\x00\x01", "application/octet-stream")
    for answer in (served, nothing, links, file):
        assert answer.headers["cache-control"] == "no-store"
    bearer = headers["Authorization"]
    assert handed == [
        ("job", grading, "compile", bearer),
        ("job", grading, "compile", bearer),
        ("report", grading, "compile", bearer, b"{}"),
        ("admits", grading, "compile", bearer),
        ("uploads", grading, "compile", bearer, b'{"files": []}'),
        ("done", grading, "compile", bearer, b"{}"),
        ("file", grading, "compile", SHA256, bearer),
    ]


@pytest.mark.parametrize(
    ("route", "bound"),
    [("", 64 * 1024), ("/uploads", 16 * MIB), ("/done", 64 * 1024)],
)
async def test_a_steps_body_past_its_bound_is_refused_before_it_is_read(
    client: httpx.AsyncClient,
    held_setup: Setup,
    monkeypatch: pytest.MonkeyPatch,
    route: str,
    bound: int,
) -> None:
    async def step_admits(*given: Any) -> None:
        pass

    monkeypatch.setattr(runs, "step_admits", step_admits)
    refused = await client.post(
        f"{_step_door(str(uuid.uuid4()))}{route}",
        content=b"x" * (bound + 1),
        headers={"Authorization": f"Bearer {STEP_TOKEN}"},
    )

    assert (refused.status_code, refused.json()["code"]) == (413, "payload_too_large")


async def test_an_upload_list_is_read_only_under_the_steps_token(
    client: httpx.AsyncClient, entered: FakeForge, held_setup: Setup
) -> None:
    grading = await _submitted(client, entered)

    refused = await client.post(
        f"{_step_door(grading)}/uploads",
        content=b"x" * (16 * MIB + 1),
        headers={"Authorization": f"Bearer {STEP_TOKEN}"},
    )

    assert (refused.status_code, refused.json()["code"]) == (401, "invalid_token")


async def test_a_step_name_no_plan_gives_is_refused_on_every_door(
    client: httpx.AsyncClient, entered: FakeForge, held_setup: Setup
) -> None:
    grading = await _submitted(client, entered)
    door = f"/api/v1/gradings/{grading}/steps/a%00b"
    headers = {"Authorization": f"Bearer {STEP_TOKEN}"}

    answers = [
        await client.get(door, headers=headers),
        await client.post(door, content=b"{}", headers=headers),
        await client.post(f"{door}/uploads", content=b'{"files": []}', headers=headers),
        await client.post(f"{door}/done", content=b"{}", headers=headers),
        await client.get(f"{door}/files/{SHA256}", headers=headers),
    ]

    assert [(a.status_code, a.json()["code"]) for a in answers] == [
        (401, "invalid_token"),
        (404, "not_found"),
        (401, "invalid_token"),
        (401, "invalid_token"),
        (401, "invalid_token"),
    ]
