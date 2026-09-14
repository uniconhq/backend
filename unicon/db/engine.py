"""The connection pool, and the separate connection `/readyz` asks with."""

import asyncio

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool

from unicon.settings import Settings


def new_engine(settings: Settings) -> AsyncEngine:
    return create_async_engine(str(settings.database_url), pool_pre_ping=True)


def new_probe_engine(settings: Settings) -> AsyncEngine:
    """A pool-less engine for `/readyz` alone. Sharing the request pool would
    report Postgres as down whenever the pool was merely busy, and an
    orchestrator would kill the busiest backend. Nothing else may use this
    engine.
    """
    return create_async_engine(str(settings.database_url), poolclass=NullPool)


async def ping(engine: AsyncEngine, timeout: float) -> None:
    """Raise if Postgres does not answer `SELECT 1` within `timeout` seconds."""
    async with asyncio.timeout(timeout), engine.connect() as connection:
        await connection.execute(text("SELECT 1"))
