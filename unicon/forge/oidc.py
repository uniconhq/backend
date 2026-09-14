"""Logging a person in through Forgejo, and keeping their token alive. The
authorization code flow with PKCE, then the identity from the userinfo endpoint
over a channel Unicon already trusts. The browser is sent to the public URL;
the back-channel calls go to the internal one.
"""

import json
import logging
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlencode

from unicon.forge.errors import ForgeRejected, ForgeTokenExpired
from unicon.forge.http import ForgeHttp
from unicon.forge.protocol import ForgeIdentity, TokenSet
from unicon.settings import Settings

logger = logging.getLogger(__name__)

AUTHORIZE_PATH = "/login/oauth/authorize"
TOKEN_PATH = "/login/oauth/access_token"
USERINFO_PATH = "/login/oauth/userinfo"
CALLBACK_PATH = "/api/v1/auth/callback"
SCOPES = "openid profile email"

SPENT_GRANT_ERRORS = frozenset({"invalid_grant", "unauthorized_client"})


class OidcClient:
    def __init__(self, settings: Settings, http: ForgeHttp) -> None:
        self._http = http
        self._client_id = settings.forge_oauth_client_id
        self._client_secret = settings.forge_oauth_client_secret.get_secret_value()
        self._public_url = str(settings.forge_public_url).rstrip("/")
        self._redirect_uri = str(settings.public_url).rstrip("/") + CALLBACK_PATH

    def authorize_url(self, *, state: str, code_challenge: str, nonce: str) -> str:
        query = urlencode(
            {
                "client_id": self._client_id,
                "redirect_uri": self._redirect_uri,
                "response_type": "code",
                "scope": SCOPES,
                "state": state,
                "nonce": nonce,
                "code_challenge": code_challenge,
                "code_challenge_method": "S256",
            }
        )
        return f"{self._public_url}{AUTHORIZE_PATH}?{query}"

    async def exchange_code(self, *, code: str, verifier: str) -> TokenSet:
        return await self._token_request(
            {
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": self._redirect_uri,
                "code_verifier": verifier,
            }
        )

    async def refresh(self, refresh_token: str) -> TokenSet:
        return await self._token_request(
            {"grant_type": "refresh_token", "refresh_token": refresh_token}
        )

    async def userinfo(self, access_token: str) -> ForgeIdentity:
        response = await self._http.request(
            "GET", USERINFO_PATH, headers={"Authorization": f"Bearer {access_token}"}
        )
        return _identity(response.json())

    async def _token_request(self, form: dict[str, str]) -> TokenSet:
        requested_at = datetime.now(UTC)
        try:
            response = await self._http.request(
                "POST",
                TOKEN_PATH,
                data=form | {"client_id": self._client_id, "client_secret": self._client_secret},
                headers={"Accept": "application/json"},
            )
        except ForgeRejected as refusal:
            error, description = _oauth_error(refusal.body)
            if error in SPENT_GRANT_ERRORS:
                raise ForgeTokenExpired(error) from refusal
            logger.error(
                "forge refused a %s grant: error=%s error_description=%s",
                form["grant_type"],
                error,
                description,
            )
            raise
        return _token_set(response.json(), requested_at)


def _oauth_error(body: str) -> tuple[str, str]:
    """RFC 6749 puts `error` and `error_description` in the body. A proxy in
    between may send neither.
    """
    try:
        payload: object = json.loads(body)
    except ValueError:
        payload = None
    if not isinstance(payload, dict):
        return "", body[:200]
    return str(payload.get("error", "")), str(payload.get("error_description", ""))


def _token_set(payload: dict[str, Any], requested_at: datetime) -> TokenSet:
    return TokenSet(
        access_token=str(payload["access_token"]),
        refresh_token=str(payload["refresh_token"]),
        expires_at=requested_at + timedelta(seconds=int(payload["expires_in"])),
    )


def _identity(claims: dict[str, Any]) -> ForgeIdentity:
    return ForgeIdentity(
        user_id=int(claims["sub"]),
        username=str(claims["preferred_username"]),
        name=_text(claims.get("name")),
        email=_text(claims.get("email")),
        avatar_url=_text(claims.get("picture")),
    )


def _text(value: object) -> str | None:
    return str(value) if value else None
