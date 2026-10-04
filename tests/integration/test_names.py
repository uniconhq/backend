"""The API speaks names and files nothing under them. The other tests file
every org, contest and task under its name; these make random keys, as a
deployment does, so a name the API answers with is known to be a name and
not a key read back out of an id. An address that names something missing
is refused like one the caller may not reach, unless they hold the role
above it.
"""

from collections.abc import AsyncIterator

import httpx
import pytest
from forge.api import orgs
from forge.testing import APP_URL, FakeForge, Setup, seed_classic

from tests.integration.conftest import ORIGIN, sign_in, sign_in_as
from unicon.main import create_app

ORG = "/api/v1/orgs/acme"
CONTEST = f"{ORG}/contests/spring"


@pytest.fixture
async def keyed(held_setup_with_random_keys: Setup) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=create_app())
    async with httpx.AsyncClient(transport=transport, base_url=APP_URL) as client:
        yield client


@pytest.fixture
async def made(
    keyed: httpx.AsyncClient, fake: FakeForge, held_setup_with_random_keys: Setup
) -> httpx.AsyncClient:
    """acme made the operator's way with ada its admin, and the contest
    acme/spring and its task sum made through the routes, ada signed in.
    """
    await orgs.create_by_operator("acme", description="Acme", admin_username="ada")
    await seed_classic(fake)
    await sign_in(keyed, fake)
    contest = await keyed.post(f"{ORG}/contests", json={"name": "spring"}, headers=ORIGIN)
    assert contest.status_code == 201, contest.json()
    task = await keyed.post(f"{CONTEST}/tasks", json={"name": "sum"}, headers=ORIGIN)
    assert task.status_code == 201, task.json()
    return keyed


async def test_the_lists_and_the_roles_answer_with_names(
    made: httpx.AsyncClient, fake: FakeForge
) -> None:
    contests = await made.get(f"{ORG}/contests")
    tasks = await made.get(f"{CONTEST}/tasks")
    me = await made.get("/api/v1/me")
    holders = await made.get(f"{CONTEST}/tasks/sum/roles")

    assert contests.json() == [{"name": "spring"}]
    assert tasks.json() == [{"name": "sum"}]
    assert me.json()["roles"] == [
        {"names": {"org": "acme", "contest": None, "task": None}, "role": "admin"}
    ]
    assert [holder["at_names"] for holder in holders.json()] == [
        {"org": "acme", "contest": None, "task": None}
    ]
    assert "acme" not in fake.state.orgs


async def test_a_missing_address_is_not_found_only_to_who_holds_the_role_above_it(
    made: httpx.AsyncClient, fake: FakeForge
) -> None:
    fake.add_user(20, "carol")

    for_ada = await made.get(f"{ORG}/contests/autumn/roles")
    await sign_in_as(made, fake, 20)
    for_carol = [
        await made.get(f"{ORG}/contests/autumn/roles"),
        await made.get(f"{CONTEST}/roles"),
        await made.get("/api/v1/orgs/nowhere/roles"),
    ]

    assert (for_ada.status_code, for_ada.json()["code"]) == (404, "not_found")
    assert [answer.status_code for answer in for_carol] == [403, 403, 403]
    assert for_carol[0].json()["detail"] == "This needs the observer role at acme/autumn."
