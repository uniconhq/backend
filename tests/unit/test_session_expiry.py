"""The three ways a session ends, and when `last_seen_at` is worth a write."""

from datetime import UTC, datetime, timedelta

import pytest

from unicon.domain.session_expiry import SessionTimes, is_expired, needs_touch

NOW = datetime(2026, 9, 12, 12, 0, tzinfo=UTC)
IDLE_TTL = timedelta(days=14)


def times(*, expires_in: timedelta, idle: timedelta, revoked: bool = False) -> SessionTimes:
    return SessionTimes(
        expires_at=NOW + expires_in,
        last_seen_at=NOW - idle,
        revoked_at=NOW - timedelta(hours=1) if revoked else None,
    )


CASES = [
    ("fresh", times(expires_in=timedelta(days=30), idle=timedelta(0)), False),
    ("used yesterday", times(expires_in=timedelta(days=20), idle=timedelta(days=1)), False),
    ("idle to the second", times(expires_in=timedelta(days=20), idle=IDLE_TTL), False),
    (
        "idle too long",
        times(expires_in=timedelta(days=20), idle=IDLE_TTL + timedelta(minutes=1)),
        True,
    ),
    ("past its hard expiry", times(expires_in=timedelta(seconds=-1), idle=timedelta(0)), True),
    ("expiring exactly now", times(expires_in=timedelta(0), idle=timedelta(0)), True),
    ("revoked", times(expires_in=timedelta(days=30), idle=timedelta(0), revoked=True), True),
]


@pytest.mark.parametrize(("name", "session", "expected"), CASES, ids=[case[0] for case in CASES])
def test_expiry_rules(name: str, session: SessionTimes, expected: bool) -> None:
    assert is_expired(session, NOW, IDLE_TTL) is expected


def test_last_seen_is_written_at_most_once_a_minute() -> None:
    assert needs_touch(NOW - timedelta(seconds=61), NOW) is True
    assert needs_touch(NOW - timedelta(seconds=10), NOW) is False
