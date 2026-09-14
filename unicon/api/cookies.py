"""The two cookies and their attributes. Both are HttpOnly and SameSite=Lax;
together with the Origin check in `api/middleware/origin.py` that is the whole
CSRF story.
"""

from fastapi import Response

from unicon.settings import Settings

SESSION_COOKIE = "unicon_session"
LOGIN_COOKIE = "unicon_login"
PATH = "/"


def set_session(response: Response, value: str, settings: Settings) -> None:
    _set(response, SESSION_COOKIE, value, int(settings.session_hard_ttl.total_seconds()), settings)


def clear_session(response: Response, settings: Settings) -> None:
    _clear(response, SESSION_COOKIE, settings)


def set_login(response: Response, value: str, settings: Settings) -> None:
    _set(response, LOGIN_COOKIE, value, int(settings.login_state_ttl.total_seconds()), settings)


def clear_login(response: Response, settings: Settings) -> None:
    _clear(response, LOGIN_COOKIE, settings)


def _set(response: Response, name: str, value: str, max_age: int, settings: Settings) -> None:
    response.set_cookie(
        name,
        value,
        max_age=max_age,
        path=PATH,
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
    )


def _clear(response: Response, name: str, settings: Settings) -> None:
    response.delete_cookie(
        name, path=PATH, httponly=True, samesite="lax", secure=settings.cookie_secure
    )
