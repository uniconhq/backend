"""Making a workflow needs a session and answers 201 with its owner and name:
under the caller's own username, or under an org where they hold the
manager role or above. An observer of the org, a person with no role there,
an org that is not there and another person's name are refused alike as
`forbidden`; a name that breaks the rules is `invalid_name`, and a name the
owner has already is `conflict`.
"""

import httpx
import pytest
from forge.api.types import Role
from forge.testing import FakeForge

from tests.integration.conftest import ACME, ORIGIN, sign_in, sign_in_as


async def test_a_person_makes_a_workflow_under_their_own_name(
    client: httpx.AsyncClient, acme: FakeForge
) -> None:
    await sign_in_as(client, acme, 8)

    made = await client.post(
        "/api/v1/workflows", json={"owner": "bob", "name": "tuned"}, headers=ORIGIN
    )

    assert made.status_code == 201, made.text
    assert made.json() == {"owner": "bob", "name": "tuned"}
    repo = acme.state.repos[("bob", "tuned.workflow")]
    assert repo.private is True
    assert repo.files["workflow.yaml"].startswith(b"# bob/tuned, a workflow.")


async def test_an_empty_new_workflow_has_no_version_and_one_problem(
    client: httpx.AsyncClient, acme: FakeForge
) -> None:
    await sign_in_as(client, acme, 8)
    await client.post("/api/v1/workflows", json={"owner": "bob", "name": "empty"}, headers=ORIGIN)
    page = (await client.get("/api/v1/workflows/bob/empty")).json()
    assert page["versions"] == []
    assert (
        page["draft"]["content"]
        == "# bob/empty, a workflow. The format is SIMPLER-CORE.md 7.\nsteps: []\n"
    )
    checked = await client.post(
        "/api/v1/workflows/check", json={"content": page["draft"]["content"]}, headers=ORIGIN
    )
    assert checked.json()["problems"] == [
        {
            "path": "steps",
            "message": "A workflow needs at least one step. Add one from the tray.",
            "step": None,
        }
    ]
    refused = await client.post(
        "/api/v1/workflows/bob/empty/versions", json={"version": "v1"}, headers=ORIGIN
    )
    assert refused.status_code == 422
    assert refused.json()["errors"] == [
        {"path": "steps", "message": "A workflow needs at least one step. Add one from the tray."}
    ]


@pytest.mark.parametrize("role", [Role.MANAGER, Role.ADMIN])
async def test_a_manager_or_admin_of_the_org_makes_one_in_the_org(
    client: httpx.AsyncClient, acme: FakeForge, role: Role
) -> None:
    await acme.orgs.grant_role(8, ACME, role)
    await sign_in_as(client, acme, 8)

    made = await client.post(
        "/api/v1/workflows", json={"owner": "acme", "name": "tuned"}, headers=ORIGIN
    )

    assert made.status_code == 201, made.text
    assert made.json() == {"owner": "acme", "name": "tuned"}
    assert ("acme", "tuned.workflow") in acme.state.repos


@pytest.mark.parametrize(
    ("observer", "owner"),
    [(True, "acme"), (False, "acme"), (False, "nowhere"), (False, "ada")],
    ids=["observer", "no role", "no such org", "another person"],
)
async def test_anyone_else_is_refused_alike(
    client: httpx.AsyncClient, acme: FakeForge, observer: bool, owner: str
) -> None:
    if observer:
        await acme.orgs.grant_role(8, ACME, Role.OBSERVER)
    await sign_in_as(client, acme, 8)

    refused = await client.post(
        "/api/v1/workflows", json={"owner": owner, "name": "tuned"}, headers=ORIGIN
    )

    assert refused.status_code == 403
    assert refused.json()["code"] == "forbidden"
    assert refused.json()["detail"] == (
        f"This needs the manager role at {owner}. Ask an admin of {owner} if you need it."
    )
    assert acme.calls_to("create_workflow") == []


async def test_a_name_that_breaks_the_rules_is_invalid(
    client: httpx.AsyncClient, acme: FakeForge
) -> None:
    await sign_in(client, acme)

    refused = await client.post(
        "/api/v1/workflows", json={"owner": "ada", "name": "Tuned!"}, headers=ORIGIN
    )

    assert refused.status_code == 422
    assert refused.json()["code"] == "invalid_name"


async def test_a_name_the_owner_has_already_is_a_conflict(
    client: httpx.AsyncClient, acme: FakeForge
) -> None:
    await sign_in(client, acme)
    body = {"owner": "acme", "name": "tuned"}
    first = await client.post("/api/v1/workflows", json=body, headers=ORIGIN)
    assert first.status_code == 201, first.text

    again = await client.post("/api/v1/workflows", json=body, headers=ORIGIN)

    assert again.status_code == 409
    assert again.json()["code"] == "conflict"


async def test_making_a_workflow_needs_a_session(client: httpx.AsyncClient) -> None:
    refused = await client.post(
        "/api/v1/workflows", json={"owner": "ada", "name": "tuned"}, headers=ORIGIN
    )

    assert refused.status_code == 401
    assert refused.json()["code"] == "unauthenticated"


async def test_making_a_workflow_needs_the_apps_origin(
    client: httpx.AsyncClient, acme: FakeForge
) -> None:
    await sign_in(client, acme)

    refused = await client.post(
        "/api/v1/workflows",
        json={"owner": "ada", "name": "tuned"},
        headers={"Origin": "http://elsewhere.test"},
    )

    assert refused.status_code == 403
    assert refused.json()["code"] == "origin_mismatch"
    assert acme.calls_to("create_workflow") == []


# Editing, versioning and sharing


async def _own(client: httpx.AsyncClient, acme: FakeForge) -> None:
    await sign_in_as(client, acme, 8)
    made = await client.post(
        "/api/v1/workflows", json={"owner": "bob", "name": "tuned"}, headers=ORIGIN
    )
    assert made.status_code == 201, made.text
    repo = acme.state.repos[("bob", "tuned.workflow")]
    acme.state.commit(
        repo, acme.state.repos[("unicon", "classic.workflow")].files, "Write workflow files", 8
    )


async def test_the_owner_reads_saves_and_versions_a_workflow(
    client: httpx.AsyncClient, acme: FakeForge
) -> None:
    await _own(client, acme)

    page = await client.get("/api/v1/workflows/bob/tuned")
    assert page.status_code == 200, page.text
    body = page.json()
    assert (body["owner"], body["name"], body["visibility"], body["editable"]) == (
        "bob",
        "tuned",
        "private",
        True,
    )
    assert (body["versions"], body["readers"]) == ([], [])
    draft = body["draft"]
    edited = draft["content"] + "# edited\n"
    saved = await client.put(
        "/api/v1/workflows/bob/tuned/draft",
        json={"content": edited, "token": draft["token"]},
        headers=ORIGIN,
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["content"] == edited
    stale = await client.put(
        "/api/v1/workflows/bob/tuned/draft",
        json={"content": "x", "token": draft["token"]},
        headers=ORIGIN,
    )
    assert stale.status_code == 409
    assert stale.json()["code"] == "conflict"

    made = await client.post(
        "/api/v1/workflows/bob/tuned/versions", json={"version": "v1"}, headers=ORIGIN
    )
    assert made.status_code == 201, made.text
    assert made.json() == {"version": "v1"}
    read = await client.get("/api/v1/workflows/bob/tuned/versions/v1")
    assert read.json() == {"content": edited}


async def test_a_version_named_other_than_v_and_a_whole_number_is_refused_at_its_name(
    client: httpx.AsyncClient, acme: FakeForge
) -> None:
    await _own(client, acme)

    refused = await client.post(
        "/api/v1/workflows/bob/tuned/versions", json={"version": "beta"}, headers=ORIGIN
    )
    made = await client.post(
        "/api/v1/workflows/bob/tuned/versions", json={"version": "v1"}, headers=ORIGIN
    )

    assert refused.status_code == 422
    assert refused.json()["code"] == "invalid_name"
    assert refused.json()["detail"] == (
        "'beta' cannot be used as a version. Name a version v and a whole number from 1, "
        "with no leading zero, such as v1, v2 or v10."
    )
    assert made.status_code == 201, made.text


async def test_a_version_of_a_draft_with_problems_is_refused_with_each_path(
    client: httpx.AsyncClient, acme: FakeForge
) -> None:
    await _own(client, acme)
    draft = (await client.get("/api/v1/workflows/bob/tuned")).json()["draft"]
    broken = draft["content"].replace("steps.compile.program", "steps.compiler.program")
    saved = await client.put(
        "/api/v1/workflows/bob/tuned/draft",
        json={"content": broken, "token": draft["token"]},
        headers=ORIGIN,
    )
    assert saved.status_code == 200, saved.text

    refused = await client.post(
        "/api/v1/workflows/bob/tuned/versions", json={"version": "v1"}, headers=ORIGIN
    )

    assert refused.status_code == 422
    assert refused.json()["code"] == "invalid_definition"
    assert refused.json()["errors"] == [
        {
            "path": "steps[1].with.program",
            "message": "There is no step called compiler before this one.",
        }
    ]


async def test_check_answers_every_problem_at_its_path_and_writes_nothing(
    client: httpx.AsyncClient, acme: FakeForge
) -> None:
    await sign_in_as(client, acme, 8)
    classic = acme.state.repos[("unicon", "classic.workflow")].files["workflow.yaml"].decode()
    unknown = classic.replace("unicon/exec@v1", "unicon/exec@v9")

    good = await client.post("/api/v1/workflows/check", json={"content": classic}, headers=ORIGIN)
    bad = await client.post("/api/v1/workflows/check", json={"content": unknown}, headers=ORIGIN)

    assert good.json() == {"problems": []}
    assert bad.status_code == 200, bad.text
    assert [problem["path"] for problem in bad.json()["problems"]] == [
        "steps[1].use",
        "steps[3].use",
    ]
    assert "cannot open unicon/exec@v9" in bad.json()["problems"][0]["message"]


async def test_a_workflow_is_shared_with_a_person_who_then_reads_it(
    client: httpx.AsyncClient, acme: FakeForge
) -> None:
    await _own(client, acme)
    await client.post(
        "/api/v1/workflows/bob/tuned/versions", json={"version": "v1"}, headers=ORIGIN
    )
    visible = await client.put(
        "/api/v1/workflows/bob/tuned/visibility", json={"visibility": "shared"}, headers=ORIGIN
    )
    assert visible.status_code == 204, visible.text
    shared = await client.put("/api/v1/workflows/bob/tuned/readers/ada", headers=ORIGIN)
    assert shared.json() == {"username": "ada"}
    page = (await client.get("/api/v1/workflows/bob/tuned")).json()
    assert (page["visibility"], page["readers"]) == ("shared", ["ada"])

    await sign_in_as(client, acme, 7)
    as_ada = await client.get("/api/v1/workflows/bob/tuned")
    assert as_ada.status_code == 200
    assert (as_ada.json()["editable"], as_ada.json()["draft"]) == (False, None)
    assert (await client.get("/api/v1/workflows/bob/tuned/versions/v1")).status_code == 200
    refused = await client.put(
        "/api/v1/workflows/bob/tuned/draft", json={"content": "x", "token": None}, headers=ORIGIN
    )
    assert refused.status_code == 403

    await sign_in_as(client, acme, 8)
    gone = await client.delete("/api/v1/workflows/bob/tuned/readers/ada", headers=ORIGIN)
    assert gone.status_code == 204
    await sign_in_as(client, acme, 7)
    hidden = await client.get("/api/v1/workflows/bob/tuned/versions/v1")
    assert hidden.status_code == 404
    assert hidden.json()["detail"] == "There is no workflow bob/tuned@v1 that you can read."


async def test_a_person_lists_what_they_may_read(
    client: httpx.AsyncClient, acme: FakeForge
) -> None:
    await _own(client, acme)

    listed = await client.get("/api/v1/workflows")

    assert listed.status_code == 200
    assert [(item["owner"], item["name"], item["editable"]) for item in listed.json()] == [
        ("bob", "tuned", True),
        ("unicon", "classic", False),
    ]


async def test_a_copy_is_a_new_private_workflow(client: httpx.AsyncClient, acme: FakeForge) -> None:
    await sign_in_as(client, acme, 8)

    copied = await client.post(
        "/api/v1/workflow-copies",
        json={"source": "unicon/classic@v3", "owner": "bob", "name": "mine"},
        headers=ORIGIN,
    )
    gone = await client.post(
        "/api/v1/workflow-combinations",
        json={"sources": ["unicon/classic@v3"], "owner": "bob", "name": "both"},
        headers=ORIGIN,
    )

    assert copied.status_code == 201, copied.text
    assert copied.json() == {"owner": "bob", "name": "mine"}
    assert acme.state.repos[("bob", "mine.workflow")].private is True
    assert gone.status_code == 404


async def test_the_primitives_are_listed_with_their_ports(
    client: httpx.AsyncClient, acme: FakeForge
) -> None:
    await sign_in_as(client, acme, 8)

    listed = await client.get("/api/v1/primitives")

    assert listed.status_code == 200
    by_ref = {item["ref"]: item for item in listed.json()}
    assert sorted(by_ref) == ["unicon/compile@v3", "unicon/exec@v1"]
    compile = by_ref["unicon/compile@v3"]
    assert (compile["batch"], compile["title"]) == (False, "Compile")
    assert compile["inputs"]["source"] == {
        "type": "folder",
        "options": None,
        "optional": False,
        "runs": True,
        "secret": False,
        "description": "The source files to compile, with their layout.",
        "outcomes": None,
        "names": None,
        "better": None,
        "at_least": None,
        "at_most": None,
        "inputs": None,
        "outputs": None,
    }
    assert compile["inputs"]["entry"]["optional"] is True
    assert compile["limits"]["memory_mb"] == 1024
    # The outcome port says what each outcome the step reports means, in
    # the declaration's order, for the step's drawer.
    assert compile["outputs"]["outcome"]["outcomes"] == {
        "accepted": "the source compiles",
        "compile_error": "it does not compile, or the compiler goes over a limit",
    }
    assert compile["problem"] is None
    # A primitive given in forms has no ports of its own: each form has its
    # ports and limits.
    run = by_ref["unicon/exec@v1"]
    assert (run["batch"], run["inputs"], run["outputs"]) == (True, {}, {})
    one = run["forms"]["one"]
    assert one["outputs_from"] == "manifest"
    assert one["inputs"]["program"]["runs"] is True
    assert one["limits_from"]["time_ms"] == {
        "input": "time_limit",
        "sum": None,
        "max": None,
        "scale": "2000",
        "add": "3000",
    }
    assert one["limits"]["memory_mb"] == 256


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("GET", "/api/v1/workflows", None),
        ("GET", "/api/v1/workflows/bob/tuned", None),
        ("PUT", "/api/v1/workflows/bob/tuned/draft", {"content": "x", "token": None}),
        ("POST", "/api/v1/workflows/bob/tuned/versions", {"version": "v1"}),
        ("GET", "/api/v1/workflows/bob/tuned/versions/v1", None),
        ("PUT", "/api/v1/workflows/bob/tuned/visibility", {"visibility": "public"}),
        ("PUT", "/api/v1/workflows/bob/tuned/readers/ada", None),
        ("DELETE", "/api/v1/workflows/bob/tuned/readers/ada", None),
        ("POST", "/api/v1/workflows/check", {"content": "x"}),
        ("POST", "/api/v1/workflow-copies", {"source": "a/b@v1", "owner": "bob", "name": "c"}),
        ("GET", "/api/v1/workflows/bob/tuned/versions/v1/box", None),
        ("GET", "/api/v1/primitives", None),
    ],
)
async def test_every_workflow_route_needs_a_session(
    client: httpx.AsyncClient, method: str, path: str, body: object
) -> None:
    refused = await client.request(method, path, json=body, headers=ORIGIN)

    assert refused.status_code == 401
    assert refused.json()["code"] == "unauthenticated"


async def test_a_version_of_a_save_someone_has_saved_over_is_a_conflict(
    client: httpx.AsyncClient, acme: FakeForge
) -> None:
    await _own(client, acme)
    draft = (await client.get("/api/v1/workflows/bob/tuned")).json()["draft"]
    first = await client.put(
        "/api/v1/workflows/bob/tuned/draft",
        json={"content": draft["content"] + "# one\n", "token": draft["token"]},
        headers=ORIGIN,
    )
    await client.put(
        "/api/v1/workflows/bob/tuned/draft",
        json={"content": draft["content"] + "# two\n", "token": first.json()["token"]},
        headers=ORIGIN,
    )

    refused = await client.post(
        "/api/v1/workflows/bob/tuned/versions",
        json={"version": "v1", "token": first.json()["token"]},
        headers=ORIGIN,
    )

    assert refused.status_code == 409
    assert refused.json()["code"] == "conflict"


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("PUT", "/api/v1/workflows/bob/tuned/draft", {"content": "x", "token": None}),
        ("POST", "/api/v1/workflows/bob/tuned/versions", {"version": "v1"}),
        ("PUT", "/api/v1/workflows/bob/tuned/visibility", {"visibility": "public"}),
        ("PUT", "/api/v1/workflows/bob/tuned/readers/ada", None),
        ("DELETE", "/api/v1/workflows/bob/tuned/readers/ada", None),
        (
            "POST",
            "/api/v1/workflow-copies",
            {"source": "unicon/classic@v3", "owner": "bob", "name": "c"},
        ),
    ],
)
async def test_someone_else_may_not_change_a_persons_workflow(
    client: httpx.AsyncClient, acme: FakeForge, method: str, path: str, body: object
) -> None:
    await _own(client, acme)
    await sign_in_as(client, acme, 7)

    refused = await client.request(method, path, json=body, headers=ORIGIN)

    assert refused.status_code == 403
    assert refused.json()["code"] == "forbidden"


_NOOP = (
    "image: ghcr.io/uniconhq/primitive-noop@sha256:" + ("0" * 64) + "\n"
    "schema_version: 6\n"
    "limits: {time_ms: 1, cpu_ms: 1, memory_mb: 1, pids: 1, output_mb: 1, gpus: 0}\n"
    "inputs:\n"
    "  note: {type: text, optional: true}\n"
    "outputs:\n"
    "  outcome: outcome\n"
    "  time_ms: {type: number, better: lower, at_least: 0}\n"
)
_HELD = """\
description: Holds a run until its limit.
inputs:
  cap: {type: number, title: Limit, unit: seconds}
  note: {type: text, optional: true, title: Note}
steps:
  - id: run
    use: unicon/noop@v1
    with:
      note: ${{ inputs.note }}
outputs:
  time_ms: ${{ steps.run.time_ms }}
"""


async def _save(client: httpx.AsyncClient, name: str, content: str, token: str | None) -> str:
    saved = await client.put(
        f"/api/v1/workflows/bob/{name}/draft",
        json={"content": content, "token": token},
        headers=ORIGIN,
    )
    assert saved.status_code == 200, saved.text
    token = saved.json()["token"]
    assert isinstance(token, str)
    return token


async def test_a_box_answers_a_workflow_version_and_one_unread(
    client: httpx.AsyncClient, acme: FakeForge
) -> None:
    acme.primitives.add("noop", {"v1": _NOOP.encode()})
    await sign_in_as(client, acme, 8)
    made = await client.post(
        "/api/v1/workflows", json={"owner": "bob", "name": "held"}, headers=ORIGIN
    )
    assert made.status_code == 201, made.text
    token = (await client.get("/api/v1/workflows/bob/held")).json()["draft"]["token"]
    token = await _save(client, "held", _HELD, token)
    version = await client.post(
        "/api/v1/workflows/bob/held/versions",
        json={"version": "v1", "token": token},
        headers=ORIGIN,
    )
    assert version.status_code == 201, version.text
    token = await _save(client, "held", _HELD + "\n", token)
    again = await client.post(
        "/api/v1/workflows/bob/held/versions",
        json={"version": "v2", "token": token},
        headers=ORIGIN,
    )
    assert again.status_code == 201, again.text

    face = await client.get("/api/v1/workflows/bob/held/versions/v1/box")
    classic = await client.get("/api/v1/workflows/unicon/classic/versions/v3/box")

    assert face.status_code == 200, face.text
    assert face.json() == {
        "run": True,
        "inputs": [
            {
                "name": "cap",
                "type": "number",
                "options": None,
                "optional": False,
                "title": "Limit",
                "unit": "seconds",
            },
            {
                "name": "note",
                "type": "text",
                "options": None,
                "optional": True,
                "title": "Note",
                "unit": None,
            },
        ],
        "outputs": [
            {
                "name": "time_ms",
                "type": "number",
                "title": None,
                "unit": None,
                "better": "lower",
                "at_least": "0",
                "at_most": None,
            }
        ],
        "newer_version": "v2",
        "description": "Holds a run until its limit.",
    }
    assert classic.status_code == 200, classic.text
    assert [each["name"] for each in classic.json()["inputs"]] == [
        "code",
        "language",
        "input",
        "answer",
        "time_limit",
        "memory_limit",
    ]
    assert [each["name"] for each in classic.json()["outputs"]] == [
        "score",
        "time_ms",
        "memory_kb",
        "log",
    ]

    await sign_in_as(client, acme, 7)
    refused = await client.get("/api/v1/workflows/bob/held/versions/v1/box")
    assert refused.status_code == 404
    assert refused.json()["code"] == "not_found"


async def test_checking_a_draft_that_holds_its_own_workflow_names_the_step(
    client: httpx.AsyncClient, acme: FakeForge
) -> None:
    acme.primitives.add("noop", {"v1": _NOOP.encode()})
    await sign_in_as(client, acme, 8)
    await client.post("/api/v1/workflows", json={"owner": "bob", "name": "held"}, headers=ORIGIN)
    token = (await client.get("/api/v1/workflows/bob/held")).json()["draft"]["token"]
    token = await _save(client, "held", _HELD, token)
    made = await client.post(
        "/api/v1/workflows/bob/held/versions",
        json={"version": "v1", "token": token},
        headers=ORIGIN,
    )
    assert made.status_code == 201, made.text
    closing = "steps:\n  - id: again\n    use: bob/held@v1\n"
    token = await _save(client, "held", closing, token)

    checked = await client.post(
        "/api/v1/workflows/check",
        json={"content": closing, "owner": "bob", "name": "held"},
        headers=ORIGIN,
    )
    refused = await client.post(
        "/api/v1/workflows/bob/held/versions",
        json={"version": "v2", "token": token},
        headers=ORIGIN,
    )

    assert checked.status_code == 200, checked.text
    assert checked.json()["problems"] == [
        {
            "path": "steps[0].use",
            "message": (
                "`again` uses bob/held@v1, and bob/held is already on that path, so the "
                "workflow would hold itself."
            ),
            "step": "again",
        }
    ]
    assert refused.status_code == 422
    assert refused.json()["code"] == "invalid_definition"
    assert refused.json()["errors"][0]["step"] == "again"
