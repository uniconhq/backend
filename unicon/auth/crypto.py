"""Session cookies and the encryption of Forgejo tokens at rest. A Forgejo token
has no scopes, so it is decrypted only inside the service about to make a call
with it.
"""

import base64
import hashlib
import secrets

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

COOKIE_BYTES = 32
NONCE_BYTES = 12


class CannotDecrypt(Exception):
    """Wrong key, or the ciphertext was changed. Either way the token is gone and
    the person has to log in again.
    """


def new_cookie_value() -> str:
    return base64.urlsafe_b64encode(secrets.token_bytes(COOKIE_BYTES)).decode().rstrip("=")


def session_id_for(cookie_value: str) -> bytes:
    """The primary key of the session row. The raw cookie is never stored."""
    return hashlib.sha256(_decode(cookie_value)).digest()


def encrypt(plaintext: str, key: bytes) -> bytes:
    nonce = secrets.token_bytes(NONCE_BYTES)
    return nonce + AESGCM(key).encrypt(nonce, plaintext.encode(), None)


def decrypt(blob: bytes, key: bytes) -> str:
    nonce, ciphertext = blob[:NONCE_BYTES], blob[NONCE_BYTES:]
    try:
        return AESGCM(key).decrypt(nonce, ciphertext, None).decode()
    except InvalidTag as exc:
        raise CannotDecrypt("the stored token does not decrypt with this key") from exc


def _decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
