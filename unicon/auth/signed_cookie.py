"""The short-lived login cookie: signed so the browser cannot edit it, and never
stored, so a login that is abandoned leaves nothing behind. None of it is
secret from its owner.
"""

from dataclasses import asdict, dataclass
from datetime import timedelta

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

SALT = "unicon-login"


class LoginCookieInvalid(Exception):
    """Missing, tampered with, or older than the login state lifetime."""


@dataclass(frozen=True)
class LoginState:
    state: str
    verifier: str
    nonce: str
    next: str


def sign(state: LoginState, key: bytes) -> str:
    return _serializer(key).dumps(asdict(state))


def unsign(value: str, key: bytes, max_age: timedelta) -> LoginState:
    try:
        payload = _serializer(key).loads(value, max_age=int(max_age.total_seconds()))
    except (BadSignature, SignatureExpired) as exc:
        raise LoginCookieInvalid(str(exc)) from exc
    if not isinstance(payload, dict):
        raise LoginCookieInvalid("not an object")
    try:
        return LoginState(**payload)
    except TypeError as exc:
        raise LoginCookieInvalid("wrong fields") from exc


def _serializer(key: bytes) -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(key, salt=SALT)
