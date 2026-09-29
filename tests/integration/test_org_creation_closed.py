"""With `UNICON_ORG_CREATION_OPEN` off, no route makes an org, and the
operator's command still does.
"""

import httpx
import pytest
from forge.testing import FakeForge, Settings

from tests.integration.conftest import ORG, ORIGIN, Command, sign_in


@pytest.fixture
def settings(settings: Settings) -> Settings:
    """Forge's test settings with org creation closed."""
    return settings.model_copy(update={"org_creation_open": False})


async def test_creating_an_org_is_refused_while_creation_is_closed(
    client: httpx.AsyncClient, forge: FakeForge
) -> None:
    await sign_in(client, forge)

    refused = await client.post("/api/v1/orgs", json={"name": "acme"}, headers=ORIGIN)

    assert refused.status_code == 403
    assert refused.json()["code"] == "forbidden"
    assert "closed" in refused.json()["detail"]
    assert (await client.get(f"{ORG}/provisioning")).status_code == 404


async def test_the_operator_still_makes_one(
    unicon: Command, forge: FakeForge, capsys: pytest.CaptureFixture[str]
) -> None:
    code = await unicon(["create-org", "acme", "--admin", "ada"])

    assert code == 0
    assert capsys.readouterr().out.startswith("Org acme: ready")
    assert "acme" in forge.state.orgs
