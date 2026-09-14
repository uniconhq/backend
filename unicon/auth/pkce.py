"""PKCE: the per-login secret proving the callback came from the browser that
started the login. Only the S256 hash goes out in the redirect, so a stolen
authorization code cannot be spent.
"""

import base64
import hashlib
import secrets

VERIFIER_BYTES = 32


def new_verifier() -> str:
    return base64.urlsafe_b64encode(secrets.token_bytes(VERIFIER_BYTES)).decode().rstrip("=")


def challenge_for(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).decode().rstrip("=")
