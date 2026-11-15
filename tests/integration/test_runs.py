"""A grading's run, read once it ended, leaves the result its contestant
then reads, with its runs and the values its scoring shows, each run with
only the fields its entry in `show` names, the organisers read whole, the
task's form then saying it has a graded submission. A source that does not
compile ends every run `compile_error` with nothing run, `compiled` 0, and
the organisers read its compile log. A run that failed on the platform's
side is delayed to its contestant and a system error to the organisers.
"""

import httpx
from forge.testing import FakeForge

from tests.integration.conftest import (
    COMPILE_LOG,
    MACHINES,
    ORIGIN,
    SOLUTION_LOG,
    TASK,
    edit_task,
    end_run,
    run_pipelines,
    sign_in_as,
    upload,
)

SOURCE = b"print(sum(map(int, input().split())))\n"
STARTER_RUN = "1704e1d77872"
"""The id of the starter's one run, a hash of its key."""
STARTER_RUNS = (
    "      runs:\n      - of: all\n        fields:\n        - verdict\n        - passed\n"
)
"""The starter's run entry: each run's verdict and `passed`, and nothing
else of it."""
EVERY_FIELD = (
    "      outputs: [compiled]\n"
    "      runs:\n"
    "        - {of: all, fields: [verdict, passed, score, time_ms, memory_kb]}\n"
)
"""`compiled` and every field of each run's result the classic workflow
gives, as soon as a grading ends."""


async def _showing_every_field(client: httpx.AsyncClient, forge: FakeForge) -> None:
    """acme/spring/sum showing `EVERY_FIELD`, saved by ada, with carol
    signed in again."""
    await sign_in_as(client, forge, 7)
    await edit_task(client, STARTER_RUNS, EVERY_FIELD)
    await sign_in_as(client, forge, 20)


async def _submitted(client: httpx.AsyncClient, forge: FakeForge, source: bytes = SOURCE) -> str:
    """carol's first submission of acme/spring/sum, of `source`; its
    grading's id."""
    made = await upload(client, forge, source)
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


async def test_a_run_reported_leaves_the_result_the_contestant_reads(
    client: httpx.AsyncClient, entered: FakeForge
) -> None:
    await _showing_every_field(client, entered)
    grading = await _submitted(client, entered)

    await run_pipelines(client)
    detail = await client.get(f"{TASK}/submissions/1")
    listed = await client.get(f"{TASK}/submissions")

    result = detail.json()["grading"]
    assert (result["id"], result["status"], result["compiled"]) == (grading, "graded", 1)
    [run] = result["runs"]
    assert (run["group"], run["place"], run["id"]) == ("all", 1, None)
    assert (run["verdict"], run["passed"]) == ("accepted", 1)
    assert {report["title"]: report for report in run["reports"]} == {
        "score": {"title": "score", "unit": None, "number": "1"},
        "Run time": {"title": "Run time", "unit": "ms", "number": "12"},
        "Memory used": {"title": "Memory used", "unit": "KB", "number": "2048"},
    }
    [score] = result["run_values"]
    assert (score["name"], score["number"], score["waiting"]) == ("score", "1", False)
    assert listed.json() == [detail.json()]


async def test_a_run_shows_only_the_fields_its_entry_names(
    client: httpx.AsyncClient, entered: FakeForge
) -> None:
    # #566: an entry names its fields, so the starter's shows each run's
    # verdict and `passed` and none of the numbers its workflow gives, and
    # `compiled` only once `outputs` lists it.
    grading = await _submitted(client, entered)

    await run_pipelines(client)
    result = (await client.get(f"{TASK}/submissions/1")).json()["grading"]

    assert (result["id"], result["status"], result["compiled"]) == (grading, "graded", None)
    [run] = result["runs"]
    assert (run["verdict"], run["passed"], run["reports"], run["texts"]) == (
        "accepted",
        1,
        [],
        {},
    )
    assert result["once"] == {"reports": {}, "texts": {}}


async def test_the_log_told_once_is_the_solutions_and_every_step_its_outcome(
    client: httpx.AsyncClient, entered: FakeForge
) -> None:
    await _submitted(client, entered)

    await run_pipelines(client)
    await sign_in_as(client, entered, 7)
    [entry] = (await client.get(f"{TASK}/gradings")).json()

    once = entry["grading"]["result"]["once"]
    assert once["outcomes"] == {"solution": "accepted", "compare": "accepted"}
    log = once["texts"]["log"]
    read = await client.get(
        f"{TASK}/organise/submissions/1/texts/{log['output']}/{log['name']}",
        params={"entrant": entry["by"]["entrant"]},
    )
    assert (read.status_code, read.text) == (200, SOLUTION_LOG)


async def test_a_source_that_does_not_compile_ends_every_run_with_nothing_run(
    client: httpx.AsyncClient, entered: FakeForge
) -> None:
    await _showing_every_field(client, entered)
    grading = await _submitted(client, entered)

    await run_pipelines(client, verdict="compile_error")
    result = (await client.get(f"{TASK}/submissions/1")).json()["grading"]
    await sign_in_as(client, entered, 7)
    [entry] = (await client.get(f"{TASK}/gradings")).json()

    assert (result["id"], result["status"], result["compiled"]) == (grading, "graded", 0)
    [run] = result["runs"]
    assert (run["verdict"], run["passed"], run["reports"]) == ("compile_error", 0, [])
    once = entry["grading"]["result"]["once"]
    # The compare after it never ran, so only the solution's outcome is told.
    assert once["outcomes"] == {"solution": "compile_error"}
    log = once["texts"]["log"]
    read = await client.get(
        f"{TASK}/organise/submissions/1/texts/{log['output']}/{log['name']}",
        params={"entrant": entry["by"]["entrant"]},
    )
    assert (read.status_code, read.text) == (200, COMPILE_LOG)


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
    assert "log" not in row and "progress" not in row
    by = entry["by"]
    assert (by["entrant_name"], by["user_id"], by["username"]) == ("carol", 20, "carol")
    assert (before["graded"], form["graded"]) == (False, True)
    result = row["result"]
    assert (result["schema_version"], result["error"]) == (6, None)
    [run] = result["runs"]
    assert (run["id"], run["verdict"], run["passed"]) == (STARTER_RUN, "accepted", 1)


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
    """The run started last ended with its first step's `outputs.json`
    not JSON, a fault of the platform's side."""
    [run] = MACHINES[client].waiting(("grading",))
    await end_run(client, run, {"solution": {"outputs.json": b"not json"}})
