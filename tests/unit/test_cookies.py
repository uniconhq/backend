"""The session cookie carries a signed id that no script can read: a signed
cookie authenticates, an altered one is refused, and the flags are as listed.
"""

import uuid

from fastapi import Request, Response
from forge.services.sign_in import SignInAttempt
from forge.settings import Settings

from unicon.api import cookies


def _request(cookie_header: str) -> Request:
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": [(b"cookie", cookie_header.encode())],
        "query_string": b"",
    }
    return Request(scope)


def _cookie_value(response: Response, name: str) -> str:
    header = response.headers["set-cookie"]
    assert header.startswith(f"{name}=")
    return header.split(";", 1)[0].split("=", 1)[1]


def test_a_signed_session_cookie_authenticates(settings: Settings) -> None:
    session_id = uuid.uuid7()
    response = Response()
    cookies.set_session(response, session_id, settings)

    value = _cookie_value(response, cookies.SESSION_COOKIE)
    assert cookies.read_session_id(_request(f"unicon_session={value}"), settings) == session_id


def test_an_altered_session_cookie_is_refused(settings: Settings) -> None:
    response = Response()
    cookies.set_session(response, uuid.uuid7(), settings)
    value = _cookie_value(response, cookies.SESSION_COOKIE)
    altered = value[:-3] + ("aaa" if not value.endswith("aaa") else "bbb")

    assert cookies.read_session_id(_request(f"unicon_session={altered}"), settings) is None
    assert cookies.read_session_id(_request(""), settings) is None


def test_a_cookie_under_another_key_is_refused(settings: Settings) -> None:
    other = Settings.for_tests(session_signing_key="AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAE")
    response = Response()
    cookies.set_session(response, uuid.uuid7(), other)
    value = _cookie_value(response, cookies.SESSION_COOKIE)

    assert cookies.read_session_id(_request(f"unicon_session={value}"), settings) is None


def test_the_flags_are_httponly_lax_and_secure_in_production(settings: Settings) -> None:
    secure = Settings.for_tests(cookie_secure=True)
    response = Response()
    cookies.set_session(response, uuid.uuid7(), secure)

    header = response.headers["set-cookie"].lower()
    assert "httponly" in header
    assert "samesite=lax" in header
    assert "secure" in header
    assert "path=/" in header


def test_the_sign_in_cookie_round_trips_the_attempt(settings: Settings) -> None:
    attempt = SignInAttempt(state="s", verifier="v", nonce="n", next="/contests/4")
    response = Response()
    cookies.set_sign_in(response, attempt, settings)
    value = _cookie_value(response, cookies.SIGN_IN_COOKIE)

    assert cookies.read_sign_in(_request(f"unicon_sign_in={value}"), settings) == attempt
    assert cookies.read_sign_in(_request("unicon_sign_in=garbage"), settings) is None
