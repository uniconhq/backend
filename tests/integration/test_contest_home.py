"""What a signed-in person reads of a contest, over HTTP: the list of contests
they see with their entrant's status, a contest's home with their
registration panel and its released tasks, each
with when it closes for them, and a released task's page with
its statement, its submission caps and the form of its inputs. A contest
they may not see and a task that is not visible answer as not found.
"""

from dataclasses import dataclass

import httpx
from forge.testing import FakeForge

from tests.integration.conftest import (
    CONTEST,
    ORIGIN,
    TASK,
    add_task,
    edit_task,
    publish,
    run_contest,
    sign_in_as,
)
from unicon.schemas.contest_home import InputField


async def test_a_signed_in_person_reads_the_home_and_a_released_task(
    client: httpx.AsyncClient, world: FakeForge
) -> None:
    await run_contest(client, visibility="signed-in")
    await publish(client)
    await sign_in_as(client, world, 20)

    listed = await client.get("/api/v1/contests")
    home = await client.get(f"{CONTEST}/home")
    page = await client.get(f"{TASK}/page")

    assert [(entry["where"], entry["status"]) for entry in listed.json()] == [
        ({"org": "acme", "contest": "spring"}, None)
    ]
    body = home.json()
    assert (body["where"], body["state"]) == ({"org": "acme", "contest": "spring"}, "published")
    panel = body["registration"]
    assert (panel["entrant"], body["organises"], panel["registration_open"]) == (
        None,
        False,
        True,
    )
    assert (panel["can_register"], panel["asks_code"], panel["refused"]) == (True, False, None)
    assert body["now"] == "2026-09-26T12:00:00Z"
    assert [(task["name"], task["label"], task["release"]["closed"]) for task in body["tasks"]] == [
        ("sum", "A", "not_approved")
    ]
    assert (body["tasks"][0]["due"], body["tasks"][0]["closes"]) == (None, body["end"])
    assert page.json()["statement"] == "Add two numbers.\n"
    assert page.json()["submissions"] == {"max": 50, "rate": {"count": 1, "per": 30}}
    assert (page.json()["due"], page.json()["closes"]) == (None, "2026-09-26T15:00:00Z")
    assert page.json()["inputs"] == [
        {
            "id": "submission",
            "type": "file",
            "label": "Your solution",
            "options": None,
            "per_test": False,
            "default": None,
                "min": None,
                "max": None,
                "max_size": 10 * 1024 * 1024,
                "parts": None,
            },
            {
                "id": "language",
                "type": "enum",
                "label": "Language",
                "options": ["python"],
                "per_test": False,
                "default": None,
                "min": None,
                "max": None,
                "max_size": 10 * 1024 * 1024,
                "parts": None,
            },
    ]


async def test_an_input_the_task_gives_no_label_reads_as_its_workflows_title(
    client: httpx.AsyncClient, world: FakeForge
) -> None:
    await run_contest(client, visibility="signed-in")
    await publish(client)
    await sign_in_as(client, world, 7)
    await edit_task(client, "submission: {label: Your solution}", "submission: {}")
    await sign_in_as(client, world, 20)

    page = await client.get(f"{TASK}/page")

    assert [(field["id"], field["label"]) for field in page.json()["inputs"]] == [
        ("submission", "Solution"),
        ("language", "Language"),
    ]


async def test_the_home_carries_the_callers_registration(
    client: httpx.AsyncClient, world: FakeForge
) -> None:
    await run_contest(client, visibility="everyone")
    await sign_in_as(client, world, 20)
    await client.post(f"{CONTEST}/entrants", json={}, headers=ORIGIN)

    home = await client.get(f"{CONTEST}/home")
    listed = await client.get("/api/v1/contests")

    assert home.json()["registration"]["entrant"]["status"] == "pending"
    assert home.json()["registration"]["refused"]["code"] == "already_registered"
    assert listed.json()[0]["status"] == "pending"


async def test_a_hidden_contest_and_an_unreleased_task_are_not_found(
    client: httpx.AsyncClient, world: FakeForge
) -> None:
    # A task made once the contest is open, not published yet.
    await run_contest(client, visibility="signed-in")
    product = await add_task(client, "product")
    await sign_in_as(client, world, 20)
    unreleased = await client.get(f"{product}/page")

    await sign_in_as(client, world, 7)
    await run_contest(client, visibility="hidden")
    await sign_in_as(client, world, 20)
    hidden = await client.get(f"{CONTEST}/home")

    assert (unreleased.status_code, unreleased.json()["code"]) == (404, "not_found")
    assert (hidden.status_code, hidden.json()["code"]) == (404, "not_found")
    assert (await client.get("/api/v1/contests")).json() == []


def test_a_task_page_keeps_each_parts_title_and_largest_size() -> None:
    @dataclass
    class _Part:
        title: str | None
        max_size: int

    @dataclass
    class _Field:
        id: str
        type: str
        label: str
        options: None = None
        per_test: bool = False
        default: None = None
        min: None = None
        max: None = None
        max_size: int = 0
        parts: tuple[_Part, ...] | None = None

    field = _Field(
        "route",
        "file",
        "Route",
        max_size=50 * 1024 * 1024,
        parts=(
            _Part("Small grid", 10 * 1024 * 1024),
            _Part("Big grid", 50 * 1024 * 1024),
        ),
    )

    shown = InputField.model_validate(field).model_dump()

    assert shown["parts"] == [
        {"title": "Small grid", "max_size": 10 * 1024 * 1024},
        {"title": "Big grid", "max_size": 50 * 1024 * 1024},
    ]
    assert shown["max_size"] == 50 * 1024 * 1024


async def test_the_contestant_reads_need_a_session(
    client: httpx.AsyncClient, world: FakeForge
) -> None:
    client.cookies.clear()

    for path in ("/api/v1/contests", f"{CONTEST}/home", f"{TASK}/page"):
        answer = await client.get(path)
        assert (answer.status_code, answer.json()["code"]) == (401, "unauthenticated"), path
