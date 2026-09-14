"""Deactivating and deleting an account. Both are mostly Forgejo operations, both
need a recent login, and both refuse while the person is the only admin of
something.
"""

from datetime import UTC, datetime, timedelta

import httpx

from tests.fakes.forge import FakeForge, FakeTeam
from tests.integration import database_probe, login_flow
from tests.integration.conftest import APP_URL

HEADERS = {"Origin": APP_URL}


def _logged_in_long_ago(database_url: str) -> None:
    database_probe.set_column(database_url, "created_at", datetime.now(UTC) - timedelta(minutes=30))


def _live_sessions(database_url: str) -> int:
    return len([row for row in database_probe.rows(database_url) if row["revoked_at"] is None])


async def test_deactivating_turns_the_forge_account_off(
    client: httpx.AsyncClient,
    browser: httpx.AsyncClient,
    forge: FakeForge,
    migrated_database_url: str,
) -> None:
    await login_flow.log_in(client, browser)

    done = await client.post("/api/v1/me/deactivate", headers=HEADERS)

    assert done.status_code == 204
    assert forge.users[7].active is False
    assert _live_sessions(migrated_database_url) == 0
    assert (await client.get("/api/v1/me")).status_code == 401


async def test_deactivating_needs_a_recent_login(
    client: httpx.AsyncClient,
    browser: httpx.AsyncClient,
    forge: FakeForge,
    migrated_database_url: str,
) -> None:
    await login_flow.log_in(client, browser)
    _logged_in_long_ago(migrated_database_url)

    refused = await client.post("/api/v1/me/deactivate", headers=HEADERS)

    assert refused.status_code == 403
    assert refused.json()["code"] == "reauth_required"
    assert forge.users[7].active is True
    assert _live_sessions(migrated_database_url) == 1


async def test_the_only_admin_of_a_team_is_refused(
    client: httpx.AsyncClient,
    browser: httpx.AsyncClient,
    forge: FakeForge,
    migrated_database_url: str,
) -> None:
    forge.teams = [FakeTeam(org="icpc", name="icpc-admin", members=["ada"])]
    await login_flow.log_in(client, browser)

    refused = await client.post("/api/v1/me/deactivate", headers=HEADERS)

    assert refused.status_code == 409
    assert refused.json()["code"] == "last_admin"
    assert refused.json()["scopes"] == [{"org": "icpc", "team": "icpc-admin"}]
    assert forge.users[7].active is True
    assert _live_sessions(migrated_database_url) == 1


async def test_an_admin_team_with_someone_else_in_it_is_fine(
    client: httpx.AsyncClient, browser: httpx.AsyncClient, forge: FakeForge
) -> None:
    forge.add_user(8, "grace")
    forge.teams = [FakeTeam(org="icpc", name="icpc-admin", members=["ada", "grace"])]
    await login_flow.log_in(client, browser)

    done = await client.post("/api/v1/me/deactivate", headers=HEADERS)

    assert done.status_code == 204


async def test_an_admin_team_past_the_first_page_still_counts(
    client: httpx.AsyncClient, browser: httpx.AsyncClient, forge: FakeForge
) -> None:
    forge.add_user(8, "grace")
    forge.teams = [
        FakeTeam(org=f"org-{index:03d}", name="readers", members=["ada", "grace"])
        for index in range(80)
    ]
    forge.teams.append(FakeTeam(org="org-055", name="org-055-admin", members=["ada"]))
    await login_flow.log_in(client, browser)

    refused = await client.post("/api/v1/me/deactivate", headers=HEADERS)

    assert refused.status_code == 409
    assert refused.json()["scopes"] == [{"org": "org-055", "team": "org-055-admin"}]


async def test_a_forge_that_caps_its_page_size_does_not_end_the_list(
    client: httpx.AsyncClient, browser: httpx.AsyncClient, forge: FakeForge
) -> None:
    forge.max_response_items = 2
    forge.add_user(8, "grace")
    forge.teams = [
        FakeTeam(org="icpc", name=f"readers-{index}", members=["ada", "grace"])
        for index in range(3)
    ]
    forge.teams.append(FakeTeam(org="icpc", name="icpc-admin", members=["ada"]))
    await login_flow.log_in(client, browser)

    refused = await client.post("/api/v1/me/deactivate", headers=HEADERS)

    assert refused.status_code == 409
    assert refused.json()["scopes"] == [{"org": "icpc", "team": "icpc-admin"}]


async def test_deleting_removes_the_forge_account(
    client: httpx.AsyncClient,
    browser: httpx.AsyncClient,
    forge: FakeForge,
    migrated_database_url: str,
) -> None:
    await login_flow.log_in(client, browser)

    done = await client.request("DELETE", "/api/v1/me", headers=HEADERS)

    assert done.status_code == 204
    assert 7 not in forge.users
    assert _live_sessions(migrated_database_url) == 0


async def test_deleting_needs_a_recent_login(
    client: httpx.AsyncClient,
    browser: httpx.AsyncClient,
    forge: FakeForge,
    migrated_database_url: str,
) -> None:
    await login_flow.log_in(client, browser)
    _logged_in_long_ago(migrated_database_url)

    refused = await client.request("DELETE", "/api/v1/me", headers=HEADERS)

    assert refused.status_code == 403
    assert refused.json()["code"] == "reauth_required"
    assert 7 in forge.users


async def test_a_forge_that_refuses_the_change_says_why(
    client: httpx.AsyncClient,
    browser: httpx.AsyncClient,
    forge: FakeForge,
    migrated_database_url: str,
) -> None:
    await login_flow.log_in(client, browser)
    forge.refusal = "user still owns 1 repository"

    refused = await client.request("DELETE", "/api/v1/me", headers=HEADERS)

    assert refused.status_code == 409
    assert refused.json()["code"] == "forge_rejected"
    assert refused.json()["detail"] == "user still owns 1 repository"
    assert 7 in forge.users
    assert _live_sessions(migrated_database_url) == 0


async def test_an_outage_before_any_change_revokes_nothing(
    client: httpx.AsyncClient,
    browser: httpx.AsyncClient,
    forge: FakeForge,
    migrated_database_url: str,
) -> None:
    await login_flow.log_in(client, browser)
    forge.unreachable = True

    failed = await client.post("/api/v1/me/deactivate", headers=HEADERS)

    assert failed.status_code == 503
    assert failed.json()["code"] == "forge_unreachable"
    assert _live_sessions(migrated_database_url) == 1
    assert (await client.get("/api/v1/me")).status_code == 200
