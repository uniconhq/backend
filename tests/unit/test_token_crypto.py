"""Forgejo tokens at rest, and the cookie that names a session."""

import base64
import hashlib

import pytest

from unicon.auth.crypto import (
    CannotDecrypt,
    decrypt,
    encrypt,
    new_cookie_value,
    session_id_for,
)

KEY = b"k" * 32
OTHER_KEY = b"j" * 32
TOKEN = "gto_a_forgejo_access_token"


def test_a_token_survives_the_round_trip() -> None:
    assert decrypt(encrypt(TOKEN, KEY), KEY) == TOKEN


def test_the_ciphertext_does_not_contain_the_token() -> None:
    assert TOKEN.encode() not in encrypt(TOKEN, KEY)


def test_the_same_token_encrypts_differently_every_time() -> None:
    assert encrypt(TOKEN, KEY) != encrypt(TOKEN, KEY)


def test_another_key_cannot_read_it() -> None:
    with pytest.raises(CannotDecrypt):
        decrypt(encrypt(TOKEN, KEY), OTHER_KEY)


def test_an_edited_ciphertext_cannot_be_read() -> None:
    blob = bytearray(encrypt(TOKEN, KEY))
    blob[-1] ^= 0xFF

    with pytest.raises(CannotDecrypt):
        decrypt(bytes(blob), KEY)


def test_a_cookie_is_32_random_bytes() -> None:
    value = new_cookie_value()

    assert len(base64.urlsafe_b64decode(value + "==")) == 32
    assert value != new_cookie_value()


def test_the_session_id_is_the_hash_of_the_cookie_bytes() -> None:
    value = new_cookie_value()

    assert session_id_for(value) == hashlib.sha256(base64.urlsafe_b64decode(value + "==")).digest()
    assert len(session_id_for(value)) == 32
