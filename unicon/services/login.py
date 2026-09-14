"""Logging in and out. People log in with their Forgejo account, and Unicon keeps
its own session cookie plus that person's Forgejo token. Nothing is written
until the code exchange has succeeded, so an abandoned login leaves no row.
"""

import logging
import secrets
from hmac import compare_digest

from sqlalchemy.ext.asyncio import AsyncSession

from unicon.auth.pkce import challenge_for, new_verifier
from unicon.auth.signed_cookie import LoginCookieInvalid, LoginState, sign, unsign
from unicon.domain.errors import ForgeMisconfigured, LoginStateInvalid, UniconError
from unicon.domain.next_path import DEFAULT_NEXT, safe_next
from unicon.forge.errors import ForgeRejected, ForgeTokenExpired, ForgeUnreachable
from unicon.forge.protocol import ForgeIdentity, Oidc, TokenSet
from unicon.services import sessions
from unicon.settings import Settings

logger = logging.getLogger(__name__)

STATE_PREFIX = 8


def start_login(settings: Settings, oidc: Oidc, next_candidate: str | None) -> tuple[str, str]:
    """Returns where to send the browser, and the login cookie to set."""
    state = LoginState(
        state=secrets.token_urlsafe(32),
        verifier=new_verifier(),
        nonce=secrets.token_urlsafe(16),
        next=safe_next(next_candidate),
    )
    url = oidc.authorize_url(
        state=state.state,
        code_challenge=challenge_for(state.verifier),
        nonce=state.nonce,
    )
    return url, sign(state, settings.session_signing_key_bytes)


async def complete_login(
    db: AsyncSession,
    settings: Settings,
    oidc: Oidc,
    *,
    code: str,
    state: str,
    login_cookie: str | None,
    session_cookie: str | None,
    ip: str | None,
    user_agent: str | None,
) -> tuple[str, str]:
    """Returns the session cookie to set, and where to land."""
    try:
        started = _login_state(settings, login_cookie)
        if not compare_digest(started.state.encode(), state.encode()):
            raise LoginStateInvalid("This login did not start here.")

        tokens = await _exchange(oidc, code=code, verifier=started.verifier)
        identity = await _identity(oidc, tokens.access_token)

        await sessions.revoke_presented(db, session_cookie)
        cookie = await sessions.create(
            db, settings, identity=identity, tokens=tokens, ip=ip, user_agent=user_agent
        )
    except ForgeUnreachable:
        logger.info("login refused: forge_unreachable (state %s)", state[:STATE_PREFIX])
        raise
    except UniconError as failure:
        logger.info("login refused: %s (state %s)", failure.code, state[:STATE_PREFIX])
        raise
    return cookie, safe_next(started.next)


def landing_after_failure(settings: Settings, login_cookie: str | None) -> str:
    """Where Try again should lead when a login did not finish. The cookie still
    holds where the person was going; one that will not open lands them on the
    front page.
    """
    try:
        return safe_next(_login_state(settings, login_cookie).next)
    except LoginStateInvalid:
        return DEFAULT_NEXT


async def logout(db: AsyncSession, session_id: bytes) -> None:
    """Only Unicon's session ends. The person stays logged into Forgejo."""
    await sessions.revoke(db, session_id)


async def _exchange(oidc: Oidc, *, code: str, verifier: str) -> TokenSet:
    try:
        return await oidc.exchange_code(code=code, verifier=verifier)
    except ForgeTokenExpired as exc:
        raise LoginStateInvalid("This login could not be completed.") from exc
    except ForgeRejected as exc:
        raise ForgeMisconfigured("The forge refused this instance.") from exc


async def _identity(oidc: Oidc, access_token: str) -> ForgeIdentity:
    try:
        return await oidc.userinfo(access_token)
    except ForgeRejected as exc:
        raise ForgeMisconfigured("The forge refused this instance.") from exc


def _login_state(settings: Settings, login_cookie: str | None) -> LoginState:
    if not login_cookie:
        raise LoginStateInvalid("This login took too long. Try again.")
    try:
        return unsign(login_cookie, settings.session_signing_key_bytes, settings.login_state_ttl)
    except LoginCookieInvalid as exc:
        raise LoginStateInvalid("This login took too long. Try again.") from exc
