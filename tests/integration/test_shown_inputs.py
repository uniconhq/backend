"""The inputs a task's `show` shows over HTTP, and the staff preview of a
draft `show` (#566). The task's page lists the runs whose inputs are shown
at a moment that has come, by the entry's `of` and the run's place there,
and the settings shown then; an input that is a file is fetched by its
address at the download door, saved under its own name, and a folder by
the address of each file it holds, by whoever reads the page, a visitor
included where the statement is public, and anything not shown now is not
found. The owner of a submission fetches the input of the first run it did
not pass, and nobody else does. The preview answers what an entrant would
read at a moment under the draft, checked alone against the publication,
with the runs it hides counted, for an observer of the task alone, and a
task never published is asked to be published first.
"""

import base64
from typing import Any

import httpx
from forge.api.uploads import Door
from forge.testing import FakeForge, Setup

from tests.integration.conftest import (
    DOES_NOT_COMPILE,
    ORIGIN,
    TASK,
    add_task,
    edit_task,
    enter,
    entrant_of,
    prepared,
    read,
    run_pipelines,
    sign_in_as,
    upload,
)

DOOR = "/-/downloads/door"
DOWNLOADS = "/-/downloads/acme/spring/sum"
STARTER_RUNS = "      runs:\n        - {of: all, fields: [verdict, passed]}\n"
"""The starter's run entry, the last lines of its `show`."""
INPUTS_SHOWN = (
    "      inputs: [time_limit]\n"
    "      runs:\n"
    "        - {of: all, fields: [input, verdict, passed]}\n"
)
"""The task's time limit, and each run's input, verdict and `passed`, shown as soon
as a grading ends, and so on the task's page from the start."""
FIRST_NOT_PASSED = f"{STARTER_RUNS}        - {{of: first_not_passed, fields: [input, verdict]}}\n"
"""The starter's run entry, and of each submission the input and verdict of
the first run it did not pass."""
PREVIEW = f"{TASK}/show-preview"
CHECKED = """\
inputs:
  code: {type: folder, title: Solution}
  language: {type: enum, options: [python], title: Language}
  input: {type: file, title: Input}
  answer: {type: file, title: Answer}
  checker: {type: folder, title: Checker}
  checker_manifest: {type: file, title: Checker's program.yaml}
  time_limit: {type: number, title: Time limit, unit: seconds}
  memory_limit: {type: number, title: Memory limit, unit: MB}
steps:
  - id: solution
    use: unicon/exec@v3
    with:
      source: ${{ inputs.code }}
      language: ${{ inputs.language }}
      stdin: ${{ inputs.input }}
      time_limit: ${{ inputs.time_limit }}
      memory_limit: ${{ inputs.memory_limit }}
  - id: compare
    use: unicon/exec@v3
    with:
      source: ${{ inputs.checker }}
      language: python
      manifest: ${{ inputs.checker_manifest }}
      time_limit: 3
      memory_limit: 256
      files:
        output: ${{ steps.solution.output }}
        answer: ${{ inputs.answer }}
outputs:
  score: ${{ steps.compare.score }}
"""
"""acme/checked: classic with the task's own checker, a folder, in place
of the diff script."""
CHECKER = {
    "checker/check.py": "print('score 1')\n",
    "checker/program.yaml": "reports:\n  score: {better: higher, at_least: 0, at_most: 1}\n",
    "checker/data/words.txt": "one\n",
}


async def _showing(client: httpx.AsyncClient, forge: FakeForge, runs: str) -> None:
    """acme/spring/sum with `runs` in place of the starter's run entry,
    saved by ada, with carol signed in again."""
    await sign_in_as(client, forge, 7)
    await edit_task(client, STARTER_RUNS, runs)
    await sign_in_as(client, forge, 20)


async def _submitted(client: httpx.AsyncClient, forge: FakeForge, source: bytes) -> None:
    """carol's first submission of acme/spring/sum, of `source`, graded."""
    made = await upload(client, forge, source)
    submitted = await client.post(
        f"{TASK}/submissions",
        json={
            "idempotency_key": "key-0001-aaaa",
            "inputs": {"code": {"uploads": [made["id"]]}, "language": {"value": "python"}},
        },
        headers=ORIGIN,
    )
    assert submitted.status_code == 201, submitted.text
    await run_pipelines(client)


async def _opened(client: httpx.AsyncClient, address: str) -> httpx.Response:
    """What the proxy asks for a download, with the header it sends."""
    return await client.get(DOOR, headers={"X-Original-URI": address})


def _door(opened: httpx.Response) -> Door:
    assert opened.status_code == 204, opened.text
    return Door(opened.headers["X-Forge-Path"], opened.headers["X-Forge-Authorization"])


async def test_the_task_page_lists_the_runs_and_settings_shown_and_serves_their_files(
    client: httpx.AsyncClient, entered: FakeForge
) -> None:
    await _showing(client, entered, INPUTS_SHOWN)

    page = (await client.get(f"{TASK}/page")).json()
    listed = await client.get(f"{TASK}/runs/all/1/inputs/input")

    assert page["shown_inputs"] == {"time_limit": 2}
    assert page["runs"] == [
        {
            "group": "all",
            "place": 1,
            "tuples": [{"title": None, "key": {"input": {"file": "tests/1.in"}}}],
        }
    ]
    address = f"{DOWNLOADS}/runs/all/1/inputs/input"
    assert listed.status_code == 200, listed.text
    assert listed.json() == {"files": [{"path": None, "download": address}]}
    opened = await _opened(client, address)
    assert await entered.content.fetch(_door(opened)) == b"1 2\n"
    # Saved under the file's own name, which the run's key already shows.
    assert opened.headers["X-Download-Disposition"] == 'attachment; filename="1.in"'


async def test_an_input_not_shown_now_is_not_found_and_its_file_not_served(
    client: httpx.AsyncClient, entered: FakeForge
) -> None:
    await _showing(client, entered, INPUTS_SHOWN)

    # The answer is not shown, there is no second run, and a setting given
    # as a number has no file; each answers as one that is not there.
    for path in (
        "runs/all/1/inputs/answer",
        "runs/all/2/inputs/input",
        "runs/sample/1/inputs/input",
        "inputs/time_limit",
        "inputs/memory_limit",
        "inputs/nothing",
    ):
        found = await client.get(f"{TASK}/{path}")
        assert (found.status_code, found.json()["code"]) == (404, "not_found"), path
        refused = await _opened(client, f"{DOWNLOADS}/{path}")
        assert refused.status_code == 403, path
        assert "X-Forge-Path" not in refused.headers
    # An address of no file's shape is refused at the door the same way:
    # no place, a place that is none, a path below a file, an empty segment.
    for path in (
        "runs/all/inputs/input",
        "runs/all/0/inputs/input",
        "runs/all/1/inputs/input/1.in",
        "runs/all/1/inputs/input/",
        "runs/all/1/inputs/%2E%2E%2Ftask.yaml",
    ):
        refused = await _opened(client, f"{DOWNLOADS}/{path}")
        assert refused.status_code == 403, path


async def test_a_visitor_fetches_a_shown_input_where_the_statement_is_public(
    client: httpx.AsyncClient, entered: FakeForge
) -> None:
    await _showing(client, entered, INPUTS_SHOWN)
    client.cookies.clear()

    statement = (await client.get("/api/v1/public/contests/acme/spring/tasks/sum")).json()
    listed = await client.get(f"{TASK}/runs/all/1/inputs/input")
    hidden = await client.get(f"{TASK}/runs/all/1/inputs/answer")
    opened = await _opened(client, f"{DOWNLOADS}/runs/all/1/inputs/input")

    assert statement["shown_inputs"] == {"time_limit": 2}
    assert [(run["group"], run["place"]) for run in statement["runs"]] == [("all", 1)]
    assert listed.status_code == 200, listed.text
    assert hidden.status_code == 404
    assert await entered.content.fetch(_door(opened)) == b"1 2\n"


async def test_the_owner_fetches_the_input_of_the_first_run_their_submission_did_not_pass(
    client: httpx.AsyncClient, entered: FakeForge, held_setup: Setup
) -> None:
    await _showing(client, entered, FIRST_NOT_PASSED)
    await _submitted(client, entered, DOES_NOT_COMPILE)

    _, run = (await client.get(f"{TASK}/submissions/1")).json()["grading"]["runs"]
    listed = await client.get(f"{TASK}/submissions/1/runs/first_not_passed/1/inputs/input")
    answer = await client.get(f"{TASK}/submissions/1/runs/first_not_passed/1/inputs/answer")
    page = (await client.get(f"{TASK}/page")).json()

    assert (run["group"], run["place"], run["verdict"]) == ("first_not_passed", 1, "compile_error")
    assert run["labelled"] == {"group": "all", "place": 1}
    address = f"{DOWNLOADS}/1/runs/first_not_passed/1/inputs/input"
    assert listed.json() == {"files": [{"path": None, "download": address}]}
    assert await entered.content.fetch(_door(await _opened(client, address))) == b"1 2\n"
    assert answer.status_code == 404
    # A submission's own run is not on the task's page.
    assert page["runs"] == []
    # Nobody else fetches it: another entrant has no such submission, and
    # with no session the door asks for one.
    entered.add_user(30, "dave")
    await enter(client, entered, held_setup, 30)
    theirs = await client.get(f"{TASK}/submissions/1/runs/first_not_passed/1/inputs/input")
    assert (theirs.status_code, theirs.json()["code"]) == (404, "not_found")
    assert (await _opened(client, address)).status_code == 403
    client.cookies.clear()
    assert (await _opened(client, address)).status_code == 401


async def _preview(client: httpx.AsyncClient, **body: Any) -> httpx.Response:
    return await client.post(PREVIEW, json=body, headers=ORIGIN)


async def test_the_preview_answers_what_an_entrant_would_read_at_a_moment(
    client: httpx.AsyncClient, entered: FakeForge
) -> None:
    await _submitted(client, entered, DOES_NOT_COMPILE)
    carols = await entrant_of(client)
    refused = await _preview(client, show={}, moment="always")
    await sign_in_as(client, entered, 7)
    draft = {
        "always": {"values": ["score"]},
        "after_deadline": {"runs": [{"of": "all", "fields": ["input", "verdict"]}]},
    }

    before = await _preview(client, show=draft, moment="always", entrant=carols, number=1)
    after = await _preview(client, show=draft, moment="after_deadline", entrant=carols, number=1)
    empty = await _preview(client, show=draft, moment="after_deadline")

    assert (refused.status_code, refused.json()["code"]) == (403, "forbidden")
    assert before.status_code == 200, before.text
    assert (before.json()["moment"], before.json()["hidden"]) == ("always", 1)
    assert before.json()["placeholders"] is None
    result = before.json()["result"]
    assert ([value["name"] for value in result["run_values"]], result["runs"]) == (["score"], [])
    # The deadline's list alone, the values listed always beside it.
    [run] = after.json()["result"]["runs"]
    assert after.json()["hidden"] == 0
    assert (run["group"], run["place"], run["verdict"], run["passed"]) == (
        "all",
        1,
        "compile_error",
        None,
    )
    assert run["tuples"] == [{"title": None, "key": {"input": {"file": "tests/1.in"}}}]
    # With no submission named, what an entrant would be shown before one.
    assert empty.json()["result"] is None
    assert empty.json()["placeholders"] == {
        "values": ["score"],
        "outputs": [],
        "inputs": {},
        "runs": [
            {
                "group": "all",
                "place": 1,
                "tuples": [{"title": None, "key": {"input": {"file": "tests/1.in"}}}],
                "fields": ["verdict"],
            }
        ],
    }


async def test_the_preview_checks_the_draft_alone_and_needs_a_publication(
    client: httpx.AsyncClient, entered: FakeForge
) -> None:
    carols = await entrant_of(client)
    await sign_in_as(client, entered, 7)

    wrong = await _preview(
        client,
        show={"always": {"values": ["nothing"], "runs": [{"of": "sample", "fields": ["verdict"]}]}},
        moment="always",
    )
    old = await _preview(client, show={"now": ["score"]}, moment="always")
    half = await _preview(client, show={}, moment="always", number=1)
    later = await add_task(client, "later")
    unpublished = await client.post(
        f"{later}/show-preview", json={"show": {}, "moment": "always"}, headers=ORIGIN
    )
    # carol has made no submission.
    missing = await _preview(client, show={}, moment="always", entrant=carols, number=1)

    assert (wrong.status_code, wrong.json()["code"]) == (422, "invalid_definition")
    assert [problem["path"] for problem in wrong.json()["errors"]] == [
        "scoring.show.always.values[0]",
        "scoring.show.always.runs[0].of",
    ]
    assert (old.status_code, old.json()["code"]) == (422, "invalid_definition")
    assert old.json()["errors"][0]["path"].startswith("scoring.show")
    assert half.status_code == 422
    assert (unpublished.status_code, unpublished.json()["detail"]) == (
        404,
        "Publish the task to preview it.",
    )
    assert missing.status_code == 404


async def _checked(client: httpx.AsyncClient, forge: FakeForge) -> None:
    """acme/spring/sum on acme/checked@v1, its checker the folder `checker/`
    and shown always among its settings, saved by ada, with carol signed in
    again."""
    await sign_in_as(client, forge, 7)
    made = await client.post(
        "/api/v1/workflows", json={"owner": "acme", "name": "checked"}, headers=ORIGIN
    )
    assert made.status_code == 201, made.text
    draft = (await client.get("/api/v1/workflows/acme/checked")).json()["draft"]
    saved = await client.put(
        "/api/v1/workflows/acme/checked/draft",
        json={"content": CHECKED, "token": draft["token"]},
        headers=ORIGIN,
    )
    assert saved.status_code == 200, saved.text
    made = await client.post(
        "/api/v1/workflows/acme/checked/versions", json={"version": "v1"}, headers=ORIGIN
    )
    assert made.status_code == 201, made.text
    task = await read(client, f"{TASK}/files/task.yaml")
    content = (
        task["content"]
        .replace("unicon/classic@v5", "acme/checked@v1")
        .replace(
            "  memory_limit: 256\n",
            "  memory_limit: 256\n  checker: checker/\n  checker_manifest: checker/program.yaml\n",
        )
        .replace(STARTER_RUNS, f"      inputs: [checker]\n{STARTER_RUNS}")
    )
    body = {
        "changes": [
            {"path": "task.yaml", "encoding": "utf-8", "content": content, "token": task["token"]},
            *(
                {
                    "path": path,
                    "encoding": "base64",
                    "content": base64.b64encode(text.encode()).decode(),
                    "token": None,
                }
                for path, text in CHECKER.items()
            ),
        ],
        "confirm": True,
    }
    saved = await client.post(f"{TASK}/save", json=body, headers=ORIGIN)
    # The contest is running, so the save asks first, naming the change of
    # workflow among what it asks about.
    assert saved.status_code == 409, saved.text
    asked = {**body, "asked": saved.json()["asked"]}
    saved = await prepared(client, await client.post(f"{TASK}/save", json=asked, headers=ORIGIN))
    assert saved.status_code == 200 and "number" in saved.json(), saved.text
    await run_pipelines(client, pipelines=("save",))
    await sign_in_as(client, forge, 20)


async def test_a_shown_folder_lists_its_files_and_serves_each_and_nothing_else(
    client: httpx.AsyncClient, entered: FakeForge
) -> None:
    await _checked(client, entered)

    page = (await client.get(f"{TASK}/page")).json()
    listed = await client.get(f"{TASK}/inputs/checker")

    assert page["shown_inputs"] == {"checker": {"folder": "checker/"}}
    # A step reads the folder, so no name in it needs quoting in its address.
    address = f"{DOWNLOADS}/inputs/checker"
    assert listed.status_code == 200, listed.text
    assert listed.json() == {
        "files": [
            {"path": "check.py", "download": f"{address}/check.py"},
            {"path": "data/words.txt", "download": f"{address}/data/words.txt"},
            {"path": "program.yaml", "download": f"{address}/program.yaml"},
        ]
    }
    opened = await _opened(client, f"{address}/data/words.txt")
    assert await entered.content.fetch(_door(opened)) == b"one\n"
    assert opened.headers["X-Download-Disposition"] == 'attachment; filename="words.txt"'
    # The folder asked for whole, a file it does not hold, and a path out of
    # it are each refused as one that is not there.
    for path in ("", "/nothing.py", "/..%2F..%2Ftask.yaml", "/../task.yaml", "/%2E%2E/task.yaml"):
        refused = await _opened(client, f"{address}{path}")
        assert refused.status_code == 403, path
        assert "X-Forge-Path" not in refused.headers
