"""The login cookie is readable by its owner and editable by nobody."""

import time
from datetime import timedelta

import pytest
from itsdangerous.timed import TimestampSigner

from unicon.auth.signed_cookie import LoginCookieInvalid, LoginState, sign, unsign

KEY = b"k" * 32
OTHER_KEY = b"j" * 32
TEN_MINUTES = timedelta(minutes=10)

STARTED = LoginState(state="s-1", verifier="v-1", nonce="n-1", next="/contests/4")


def test_a_login_state_survives_the_round_trip() -> None:
    assert unsign(sign(STARTED, KEY), KEY, TEN_MINUTES) == STARTED


def test_an_edited_cookie_is_refused() -> None:
    signed = sign(STARTED, KEY)
    edited = ("a" if signed[0] != "a" else "b") + signed[1:]

    with pytest.raises(LoginCookieInvalid):
        unsign(edited, KEY, TEN_MINUTES)


def test_a_cookie_signed_with_another_key_is_refused() -> None:
    with pytest.raises(LoginCookieInvalid):
        unsign(sign(STARTED, OTHER_KEY), KEY, TEN_MINUTES)


def test_a_cookie_older_than_the_window_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(TimestampSigner, "get_timestamp", lambda _: int(time.time()) - 3600)
    stale = sign(STARTED, KEY)
    monkeypatch.undo()

    with pytest.raises(LoginCookieInvalid):
        unsign(stale, KEY, TEN_MINUTES)


def test_nonsense_is_refused() -> None:
    with pytest.raises(LoginCookieInvalid):
        unsign("not-a-cookie", KEY, TEN_MINUTES)
