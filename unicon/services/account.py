"""The three things a person can do to their own account. With no users table this
is all Forgejo's state; Unicon only revokes its own sessions.
"""

import json
from collections.abc import Awaitable
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from unicon.domain.errors import (
    ForgeReauthRequired,
    ForgeRejectedChange,
    LastAdmin,
    NotFoundError,
    ReauthRequired,
)
from unicon.domain.identity import ActiveSession
from unicon.forge.admin import UserNotFound
from unicon.forge.errors import ForgeRejected, ForgeUnreachable
from unicon.forge.protocol import Admin, Oidc, TeamMembership
from unicon.log import get_logger
from unicon.schemas.account import Me
from unicon.services import sessions
from unicon.settings import Settings

log = get_logger(__name__)

OWNERS_TEAM = "Owners"
ADMIN_TEAM_SUFFIX = "-admin"


async def me(db: AsyncSession, settings: Settings, session: ActiveSession, oidc: Oidc) -> Me:
    try:
        token = await sessions.forge_token_for(db, settings, session.id, oidc)
        identity = await oidc.userinfo(token)
    except ForgeRejected as exc:
        log.warning("forge.userinfo_refused", user_id=session.user_id)
        await sessions.revoke(db, session.id)
        raise ForgeReauthRequired("Sign in again.") from exc
    except ForgeUnreachable:
        return Me(
            user_id=session.user_id,
            username=session.username,
            name=None,
            avatar_url=None,
            email=None,
            degraded=True,
        )
    return Me(
        user_id=identity.user_id,
        username=identity.username,
        name=identity.name,
        avatar_url=identity.avatar_url,
        email=identity.email,
        degraded=False,
    )


async def deactivate(
    db: AsyncSession, settings: Settings, session: ActiveSession, admin: Admin
) -> None:
    """An inactive Forgejo user cannot log in, push or complete OIDC, so they
    cannot get a new session either.
    """
    username = await _prepare(db, settings, session, admin)
    await _apply(admin.set_active(username, False))


async def delete(
    db: AsyncSession, settings: Settings, session: ActiveSession, admin: Admin
) -> None:
    """Results stay: `judgings` keeps the Forgejo user id after the account is
    gone.
    """
    username = await _prepare(db, settings, session, admin)
    await _apply(admin.delete_user(username))


async def _prepare(
    db: AsyncSession, settings: Settings, session: ActiveSession, admin: Admin
) -> str:
    """The checks both actions share, and the revocation both do first. Sessions
    go before the Forgejo call on purpose: if that call then fails, the person
    is signed out but still active, which is the safe half of a half-done
    change.
    """
    _require_recent_login(session, settings)
    username = await _current_username(session, admin)
    _refuse_if_last_admin(await admin.teams_of(username))
    await sessions.revoke_all(db, session.user_id)
    return username


def _require_recent_login(session: ActiveSession, settings: Settings) -> None:
    """Unicon has no password to ask for, so a recent trip through Forgejo is the
    proof. `created_at` is when that happened.
    """
    if datetime.now(UTC) - session.created_at > settings.reauth_window:
        raise ReauthRequired("Sign in again to change your account.")


async def _current_username(session: ActiveSession, admin: Admin) -> str:
    """By id, not by the cached name: Forgejo sends no event on a rename."""
    try:
        return await admin.username_for(session.user_id)
    except UserNotFound as exc:
        raise NotFoundError("This account no longer exists.") from exc


def _refuse_if_last_admin(memberships: list[TeamMembership]) -> None:
    """There are no orgs yet, so this passes trivially. It exists so the rule is
    in place before the data is.
    """
    blocking = [
        {"org": membership.org, "team": membership.team}
        for membership in memberships
        if _is_admin_team(membership.team) and membership.member_count <= 1
    ]
    if blocking:
        raise LastAdmin("Someone else has to be an admin of these first.", scopes=blocking)


def _is_admin_team(team: str) -> bool:
    return team == OWNERS_TEAM or team.endswith(ADMIN_TEAM_SUFFIX)


async def _apply(call: Awaitable[None]) -> None:
    """The sessions are already revoked, so a failure here is reported as it is.
    Forgejo saying no is not Forgejo being down: a refusal carries a reason the
    person can act on, so its message is passed through.
    """
    try:
        await call
    except ForgeRejected as exc:
        log.warning("forge.account_change_refused", reason=exc.body[:200])
        raise ForgeRejectedChange(_reason(exc)) from exc


def _reason(rejection: ForgeRejected) -> str:
    """Forgejo puts its reason in a `message` field; anything else is text."""
    try:
        body: object = json.loads(rejection.body)
    except ValueError:
        body = None
    if isinstance(body, dict):
        message = body.get("message")
        if isinstance(message, str):
            return message
    return rejection.body[:200]
