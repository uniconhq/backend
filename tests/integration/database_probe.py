"""Looking at the `sessions` table from outside the app. A test that wants to know
what was stored, or to age a row, goes around the app rather than through it.
"""

from datetime import datetime
from typing import Any

import psycopg


def rows(database_url: str) -> list[dict[str, Any]]:
    with psycopg.connect(_dsn(database_url)) as db:
        cursor = db.execute(
            "select id, user_id, username, forge_access_token, forge_refresh_token,"
            " forge_token_expires_at, created_at, revoked_at from sessions order by created_at"
        )
        names = [column.name for column in cursor.description or []]
        return [dict(zip(names, row, strict=True)) for row in cursor.fetchall()]


def count(database_url: str) -> int:
    return len(rows(database_url))


def set_column(database_url: str, column: str, value: datetime) -> None:
    """Aging a row is how a test reaches a moment it would otherwise wait for."""
    with psycopg.connect(_dsn(database_url), autocommit=True) as db:
        db.execute(f"update sessions set {column} = %s", (value,))


def _dsn(database_url: str) -> str:
    return database_url.replace("postgresql+psycopg://", "postgresql://")
