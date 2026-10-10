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
    assert refused.json()["detail"] == f"This needs the manager role at {owner}."
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


async def test_a_version_of_a_draft_with_problems_is_refused_with_each_path(
    client: httpx.AsyncClient, acme: FakeForge
) -> None:
    await _own(client, acme)
    draft = (await client.get("/api/v1/workflows/bob/tuned")).json()["draft"]
    broken = draft["content"].replace("steps.compile.binary", "steps.compiler.binary")
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
        {"path": "steps[1].with.binary", "message": "compiler is not a step before this one."}
    ]


async def test_check_answers_every_problem_at_its_path_and_writes_nothing(
    client: httpx.AsyncClient, acme: FakeForge
) -> None:
    await sign_in_as(client, acme, 8)
    classic = acme.state.repos[("unicon", "classic.workflow")].files["workflow.yaml"].decode()
    uses_workflow = classic.replace("unicon/diff-check@v2", "unicon/classic@v2")

    good = await client.post("/api/v1/workflows/check", json={"content": classic}, headers=ORIGIN)
    bad = await client.post(
        "/api/v1/workflows/check", json={"content": uses_workflow}, headers=ORIGIN
    )

    assert good.json() == {"problems": []}
    assert bad.status_code == 200, bad.text
    (problem,) = bad.json()["problems"]
    assert problem["path"] == "steps[2].use"
    assert "is not a primitive" in problem["message"]


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
    assert hidden.json()["detail"] == "There is no workflow bob/tuned@v1 you may read."


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


async def test_a_copy_and_a_combination_are_new_private_workflows(
    client: httpx.AsyncClient, acme: FakeForge
) -> None:
    await sign_in_as(client, acme, 8)
    classic = "unicon/classic@v2"

    copied = await client.post(
        "/api/v1/workflow-copies",
        json={"source": classic, "owner": "bob", "name": "mine"},
        headers=ORIGIN,
    )
    combined = await client.post(
        "/api/v1/workflow-combinations",
        json={"sources": [classic, classic], "owner": "bob", "name": "both"},
        headers=ORIGIN,
    )
    one = await client.post(
        "/api/v1/workflow-combinations",
        json={"sources": [classic], "owner": "bob", "name": "one"},
        headers=ORIGIN,
    )

    assert copied.status_code == 201, copied.text
    assert copied.json() == {"owner": "bob", "name": "mine"}
    assert combined.status_code == 201, combined.text
    assert acme.state.repos[("bob", "both.workflow")].private is True
    assert one.status_code == 422
    assert one.json()["code"] == "rejected"


async def test_the_primitives_are_listed_with_their_ports(
    client: httpx.AsyncClient, acme: FakeForge
) -> None:
    await sign_in_as(client, acme, 8)

    listed = await client.get("/api/v1/primitives")

    assert listed.status_code == 200
    by_ref = {item["ref"]: item for item in listed.json()}
    assert sorted(by_ref) == [
        "unicon/compile@v2",
        "unicon/diff-check@v2",
        "unicon/sandbox-run@v2",
    ]
    run = by_ref["unicon/sandbox-run@v2"]
    assert run["batch"] is True
    assert run["inputs"]["binary"] == {
        "type": "file",
        "options": None,
        "optional": False,
        "runs": True,
        "secret": False,
    }
    assert run["inputs"]["args"]["optional"] is True
    assert run["limits_from"]["time_ms"] == {
        "input": "time_limit",
        "scale": "2000",
        "add": "3000",
    }
    assert run["limits"]["memory_mb"] == 256
    assert "outcome" in run["outputs"]
    assert run["problem"] is None


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
        (
            "POST",
            "/api/v1/workflow-combinations",
            {"sources": ["a/b@v1"], "owner": "bob", "name": "c"},
        ),
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
            {"source": "unicon/classic@v2", "owner": "bob", "name": "c"},
        ),
        (
            "POST",
            "/api/v1/workflow-combinations",
            {"sources": ["unicon/classic@v2", "unicon/classic@v2"], "owner": "bob", "name": "c"},
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
