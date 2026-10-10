"""The operator's two commands, run as `unicon ...` over the fake: an org
made whatever the setting says, with its named admin able to administer it,
an org that fails halfway refused with its reason, a description
longer than the forge takes refused before forge is called, and an account
whose first password is printed once and which then signs in.
"""

import httpx
import pytest
from forge.api.errors import Unavailable
from forge.api.types import Role
from forge.testing import FakeForge

from tests.integration.conftest import ACME, ORG, ORIGIN, Command, sign_in_as


async def test_create_org_makes_a_ready_org_its_admin_can_administer(
    unicon: Command,
    forge: FakeForge,
    client: httpx.AsyncClient,
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = await unicon(["create-org", "acme", "--admin", "bob", "--description", "Acme"])

    assert code == 0
    assert capsys.readouterr().out == "Org acme made, with bob its admin.\n"
    org = forge.state.orgs["acme"]
    assert (org.description, org.labels != set(), org.event_push is not None) == (
        "Acme",
        True,
        True,
    )
    assert 8 in org.roles[(ACME, Role.ADMIN)]

    await sign_in_as(client, forge, 8)
    changed = await client.patch(ORG, json={"description": "Ours"}, headers=ORIGIN)
    assert changed.status_code == 204


async def test_create_org_names_an_admin_the_forge_does_not_know(
    unicon: Command, forge: FakeForge, capsys: pytest.CaptureFixture[str]
) -> None:
    code = await unicon(["create-org", "acme", "--admin", "nobody"])

    assert code == 1
    assert capsys.readouterr().err == "There is no user named 'nobody' at the forge.\n"
    assert "acme" not in forge.state.orgs


async def test_create_org_that_fails_halfway_is_refused_with_its_reason(
    unicon: Command,
    forge: FakeForge,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def gone(*args: object, **kwargs: object) -> object:
        raise Unavailable("the CI went away")

    monkeypatch.setattr(forge.grading, "set_up_org", gone)

    code = await unicon(["create-org", "acme", "--admin", "ada"])

    assert code == 1
    assert capsys.readouterr().err == (
        "The forge or the CI did not answer; try again in a moment.\n"
    )


async def test_create_account_prints_the_first_password_once_and_the_account_signs_in(
    unicon: Command,
    forge: FakeForge,
    client: httpx.AsyncClient,
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = await unicon(["create-account", "carol", "--email", "carol@example.test"])

    assert code == 0
    user = forge.state.user_named("carol")
    assert capsys.readouterr().out == (
        f"Account carol created, user id {user.id}.\n"
        f"First password: {forge.state.passwords[user.id]}\n"
        "It is shown only this once and must be changed at the first sign-in.\n"
    )
    (made,) = forge.calls_to("create_user")
    assert made.arguments["must_change_password"] is True

    await sign_in_as(client, forge, user.id)
    me = await client.get("/api/v1/me")
    assert (me.json()["user"]["username"], me.json()["roles"]) == ("carol", [])


async def test_create_account_refuses_a_service_account_name(
    unicon: Command, forge: FakeForge, capsys: pytest.CaptureFixture[str]
) -> None:
    code = await unicon(["create-account", "unicon-ci-acme", "--email", "x@example.test"])

    assert code == 1
    assert "reserved for org service accounts" in capsys.readouterr().err
    assert forge.calls_to("create_user") == []


async def test_create_org_refuses_a_description_over_255_characters_before_forge(
    unicon: Command, forge: FakeForge, capsys: pytest.CaptureFixture[str]
) -> None:
    code = await unicon(["create-org", "acme", "--admin", "ada", "--description", "x" * 256])

    assert code == 1
    assert capsys.readouterr().err == (
        "The description is longer than 255 characters, the most the forge takes.\n"
    )
    assert forge.calls == []
