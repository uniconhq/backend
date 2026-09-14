"""`/healthz` is about the process, `/readyz` is about Postgres."""

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.exc import TimeoutError as PoolTimeout
from sqlalchemy.ext.asyncio import create_async_engine

from tests.integration.running_app import running_app
from unicon.db.engine import new_probe_engine, ping
from unicon.settings import Settings

NOTHING_LISTENING = "postgresql+psycopg://unicon:unicon@127.0.0.1:1/unicon"
ONE_CONNECTION = {"pool_size": 1, "max_overflow": 0, "pool_timeout": 1}


async def test_healthz_is_ok(client: AsyncClient) -> None:
    response = await client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_readyz_is_ready_when_postgres_answers(client: AsyncClient) -> None:
    response = await client.get("/readyz")

    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


async def test_readyz_is_503_when_postgres_does_not_answer() -> None:
    settings = Settings.for_tests(database_url=NOTHING_LISTENING)

    async with running_app(settings) as app:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            ready = await client.get("/readyz")
            healthy = await client.get("/healthz")

    assert ready.status_code == 503
    assert ready.json()["status"] == "not_ready"
    assert ready.json()["postgres"]
    assert healthy.status_code == 200


async def test_a_full_pool_is_not_a_dead_backend(settings: Settings) -> None:
    """The readiness probe asks on a connection of its own. A backend under load
    has every pooled connection checked out, and one that answered `not_ready`
    then would be restarted for working too hard.
    """
    busy = create_async_engine(str(settings.database_url), **ONE_CONNECTION)
    probe = new_probe_engine(settings)
    try:
        async with busy.connect():
            with pytest.raises(PoolTimeout):
                await ping(busy, timeout=5.0)

            await ping(probe, timeout=5.0)
    finally:
        await busy.dispose()
        await probe.dispose()
