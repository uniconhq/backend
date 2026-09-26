"""The two cookies. The session cookie carries a session id and nothing else,
signed under `UNICON_SESSION_SIGNING_KEY` so a forged id is refused without a
database read. The sign-in cookie carries what checks a sign-in's answer, for
the few minutes a sign-in takes. Both are `HttpOnly`, `SameSite=Lax` and
`Secure` in production, and first-party because the app and the API share one
origin.
"""

import uuid
from dataclasses import asdict
from datetime import timedelta

from fastapi import Request, Response
from forge.services.sign_in import SignInAttempt
from forge.settings import Settings
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

SESSION_COOKIE = "unicon_session"
SIGN_IN_COOKIE = "unicon_sign_in"
PATH = "/"

SESSION_SALT = "unicon-session"
SIGN_IN_SALT = "unicon-sign-in"


def set_session(response: Response, session_id: uuid.UUID, settings: Settings) -> None:
    value = _serializer(settings, SESSION_SALT).dumps(session_id.hex)
    _set(response, SESSION_COOKIE, value, settings.session_hard_ttl, settings)


def clear_session(response: Response, settings: Settings) -> None:
    _clear(response, SESSION_COOKIE, settings)


def read_session_id(request: Request, settings: Settings) -> uuid.UUID | None:
    """The session id the request carries, or none when there is no cookie or
    its signature does not hold.
    """
    value = request.cookies.get(SESSION_COOKIE)
    if not value:
        return None
    try:
        raw = _serializer(settings, SESSION_SALT).loads(
            value, max_age=_seconds(settings.session_hard_ttl)
        )
        return uuid.UUID(hex=str(raw))
    except BadSignature, SignatureExpired, ValueError:
        return None


def set_sign_in(response: Response, attempt: SignInAttempt, settings: Settings) -> None:
    value = _serializer(settings, SIGN_IN_SALT).dumps(asdict(attempt))
    _set(response, SIGN_IN_COOKIE, value, settings.sign_in_ttl, settings)


def clear_sign_in(response: Response, settings: Settings) -> None:
    _clear(response, SIGN_IN_COOKIE, settings)


def read_sign_in(request: Request, settings: Settings) -> SignInAttempt | None:
    value = request.cookies.get(SIGN_IN_COOKIE)
    if not value:
        return None
    try:
        payload = _serializer(settings, SIGN_IN_SALT).loads(
            value, max_age=_seconds(settings.sign_in_ttl)
        )
        return SignInAttempt(**payload)
    except BadSignature, SignatureExpired, TypeError, ValueError:
        return None


def _serializer(settings: Settings, salt: str) -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(settings.session_signing_key_bytes, salt=salt)


def _seconds(lifetime: timedelta) -> int:
    return int(lifetime.total_seconds())


def _set(
    response: Response, name: str, value: str, lifetime: timedelta, settings: Settings
) -> None:
    response.set_cookie(
        name,
        value,
        max_age=_seconds(lifetime),
        path=PATH,
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
    )


def _clear(response: Response, name: str, settings: Settings) -> None:
    response.delete_cookie(
        name, path=PATH, httponly=True, samesite="lax", secure=settings.cookie_secure
    )
