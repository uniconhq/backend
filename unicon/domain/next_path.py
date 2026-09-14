"""Where a login is allowed to land. `?next=` comes from the browser, so only a
path on this site is accepted: `//host` is a URL, not a path.
"""

DEFAULT_NEXT = "/"

MAX_LENGTH = 2048


def safe_next(candidate: str | None) -> str:
    if not candidate or not candidate.startswith("/"):
        return DEFAULT_NEXT
    if len(candidate) > MAX_LENGTH:
        return DEFAULT_NEXT
    if candidate.startswith("//") or candidate.startswith("/\\"):
        return DEFAULT_NEXT
    if "\n" in candidate or "\r" in candidate:
        return DEFAULT_NEXT
    return candidate
