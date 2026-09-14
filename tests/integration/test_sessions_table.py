"""A row goes into `sessions` and comes back the same. The columns worth proving
are the ones Postgres is picky about: a bytea key, an inet address, and
timestamps that keep their timezone.
"""

import hashlib
from datetime import UTC, datetime, timedelta
from ipaddress import ip_address

from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine

from unicon.db.session import new_session_factory
from unicon.models import Session


async def test_a_session_round_trips(migrated_database_url: str) -> None:
    engine = create_async_engine(migrated_database_url)
    created = datetime.now(UTC)
    cookie = b"\x01" * 32
    row = Session(
        id=hashlib.sha256(cookie).digest(),
        user_id=42,
        username="ada",
        forge_access_token=b"ciphertext-access",
        forge_refresh_token=b"ciphertext-refresh",
        forge_token_expires_at=created + timedelta(hours=1),
        created_at=created,
        expires_at=created + timedelta(days=30),
        last_seen_at=created,
        ip=ip_address("2001:db8::1"),
        user_agent="a browser",
    )

    try:
        factory = new_session_factory(engine)
        async with factory() as db:
            db.add(row)
            await db.commit()
        async with factory() as db:
            found = (await db.execute(select(Session))).scalar_one()

            assert found.id == hashlib.sha256(cookie).digest()
            assert found.user_id == 42
            assert found.ip == ip_address("2001:db8::1")
            assert found.revoked_at is None
            assert found.expires_at.tzinfo is not None
            assert found.expires_at == created + timedelta(days=30)
    finally:
        await engine.dispose()
