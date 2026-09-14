"""The clock endpoint answers in UTC."""

from datetime import UTC, datetime

import pytest
from httpx import ASGITransport, AsyncClient

from unicon.main import create_app
from unicon.settings import Settings


@pytest.fixture
async def client(settings: Settings) -> AsyncClient:
    app = create_app(settings)
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def test_server_time_is_utc_and_close_to_now(client: AsyncClient) -> None:
    response = await client.get("/api/v1/time")

    assert response.status_code == 200
    now = datetime.fromisoformat(response.json()["now"])
    assert now.tzinfo is not None
    assert now.utcoffset() == UTC.utcoffset(None)
    assert abs((datetime.now(UTC) - now).total_seconds()) < 60
