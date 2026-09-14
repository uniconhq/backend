"""When a session stops counting: revoked, past its hard expiry, or unused for too
long. Checked in that order, because the first that applies is the most
specific thing to tell the person.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta

TOUCH_INTERVAL = timedelta(minutes=1)


@dataclass(frozen=True)
class SessionTimes:
    expires_at: datetime
    last_seen_at: datetime
    revoked_at: datetime | None


def is_expired(times: SessionTimes, now: datetime, idle_ttl: timedelta) -> bool:
    if times.revoked_at is not None:
        return True
    if now >= times.expires_at:
        return True
    return now - times.last_seen_at > idle_ttl


def needs_touch(last_seen_at: datetime, now: datetime) -> bool:
    return now - last_seen_at >= TOUCH_INTERVAL
