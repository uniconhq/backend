"""The migration runs on an empty database, and runs back off it."""

import psycopg

from unicon.db.migrations import downgrade_to_base, upgrade_to_head

NINE_TABLES = {
    "sessions",
    "participants",
    "teams",
    "team_members",
    "invites",
    "entrant_repos",
    "judgings",
    "uploads",
    "jupyter_sessions",
}


def _table_names(database_url: str) -> set[str]:
    with psycopg.connect(database_url.replace("postgresql+psycopg://", "postgresql://")) as db:
        rows = db.execute(
            "select table_name from information_schema.tables where table_schema = 'public'"
        ).fetchall()
    return {str(row[0]) for row in rows}


def test_upgrade_creates_the_nine_tables(database_url: str) -> None:
    upgrade_to_head(database_url)

    assert _table_names(database_url) >= NINE_TABLES


def test_downgrade_leaves_an_empty_database(database_url: str) -> None:
    upgrade_to_head(database_url)

    downgrade_to_base(database_url)

    assert _table_names(database_url) & NINE_TABLES == set()


def test_upgrade_is_repeatable_after_a_downgrade(database_url: str) -> None:
    upgrade_to_head(database_url)
    downgrade_to_base(database_url)

    upgrade_to_head(database_url)

    assert _table_names(database_url) >= NINE_TABLES
