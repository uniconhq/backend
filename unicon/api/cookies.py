"""The two cookies as HTTP: their names, their flags and the `Set-Cookie`
header. What goes into them, and the key that signs it, are forge's; this
module puts forge's string into a header and hands back the one a request
carries. Both are `HttpOnly` and `SameSite=Lax`, `Secure` as forge's policy
says, and first-party because the app and the API share one origin.
"""

import uuid

from fastapi import Request, Response
from forge.api.cookies import (
    policy,
    session_id,
    session_value,
    sign_in_attempt,
    sign_in_value,
)
from forge.api.sign_in import SignInAttempt
from forge.api.types import Session

SESSION_COOKIE = "unicon_session"
SIGN_IN_COOKIE = "unicon_sign_in"
PATH = "/"


def set_session(response: Response, session: Session) -> None:
    _set(response, SESSION_COOKIE, session_value(session), policy().session_max_age)


def clear_session(response: Response) -> None:
    _clear(response, SESSION_COOKIE)


def read_session_id(request: Request) -> uuid.UUID | None:
    """The session id the request carries, or none when there is no cookie or
    it does not hold.
    """
    return session_id(request.cookies.get(SESSION_COOKIE))


def set_sign_in(response: Response, attempt: SignInAttempt) -> None:
    _set(response, SIGN_IN_COOKIE, sign_in_value(attempt), policy().sign_in_max_age)


def clear_sign_in(response: Response) -> None:
    _clear(response, SIGN_IN_COOKIE)


def read_sign_in(request: Request) -> SignInAttempt | None:
    return sign_in_attempt(request.cookies.get(SIGN_IN_COOKIE))


def _set(response: Response, name: str, value: str, max_age: int) -> None:
    response.set_cookie(
        name,
        value,
        max_age=max_age,
        path=PATH,
        httponly=True,
        samesite="lax",
        secure=policy().secure,
    )


def _clear(response: Response, name: str) -> None:
    response.delete_cookie(name, path=PATH, httponly=True, samesite="lax", secure=policy().secure)
