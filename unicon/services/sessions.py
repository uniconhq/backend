"""Unicon's own sessions: making one, checking one, ending one, and keeping the
Forgejo token inside it usable. The only place the `sessions` table is read or
written, and the only place a token is decrypted.
"""

import asyncio
import weakref
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import CursorResult, Update, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from unicon.auth.crypto import CannotDecrypt, decrypt, encrypt, new_cookie_value, session_id_for
from unicon.domain.client_address import client_address
from unicon.domain.errors import (
    ForgeMisconfigured,
    ForgeReauthRequired,
    NotFoundError,
    SessionExpired,
    Unauthenticated,
)
from unicon.domain.identity import ActiveSession
from unicon.domain.session_expiry import SessionTimes, is_expired, needs_touch
from unicon.forge.errors import ForgeRejected, ForgeTokenExpired
from unicon.forge.protocol import ForgeIdentity, Oidc, TokenSet
from unicon.log import get_logger
from unicon.models import Session
from unicon.schemas.account import SessionInfo
from unicon.settings import Settings

log = get_logger(__name__)

REFRESH_MARGIN = timedelta(minutes=5)

NO_TOKEN = b""

_refreshing: weakref.WeakValueDictionary[bytes, asyncio.Lock] = weakref.WeakValueDictionary()


@dataclass(frozen=True)
class _Tokens:
    """The token columns read out of the row, so no connection stays checked out
    while Forgejo is called.
    """

    access: bytes
    refresh: bytes
    expires_at: datetime


async def create(
    db: AsyncSession,
    settings: Settings,
    *,
    identity: ForgeIdentity,
    tokens: TokenSet,
    ip: str | None,
    user_agent: str | None,
) -> str:
    """Returns the cookie value. It is the only time it exists in Unicon."""
    now = datetime.now(UTC)
    cookie = new_cookie_value()
    key = settings.token_encryption_key_bytes
    db.add(
        Session(
            id=session_id_for(cookie),
            user_id=identity.user_id,
            username=identity.username,
            forge_access_token=encrypt(tokens.access_token, key),
            forge_refresh_token=encrypt(tokens.refresh_token, key),
            forge_token_expires_at=tokens.expires_at,
            created_at=now,
            expires_at=now + settings.session_hard_ttl,
            last_seen_at=now,
            ip=client_address(ip),
            user_agent=user_agent,
        )
    )
    await db.commit()
    return cookie


async def authenticate(db: AsyncSession, settings: Settings, cookie: str) -> ActiveSession:
    now = datetime.now(UTC)
    row = await _row(db, _id_of(cookie))
    if row is None:
        raise Unauthenticated("No session.")
    if is_expired(_times(row), now, settings.session_idle_ttl):
        raise SessionExpired("This session has ended.")
    if needs_touch(row.last_seen_at, now):
        row.last_seen_at = now
        await db.commit()
    return ActiveSession(
        id=row.id, user_id=row.user_id, username=row.username, created_at=row.created_at
    )


async def forge_token_for(
    db: AsyncSession, settings: Settings, session_id: bytes, oidc: Oidc
) -> str:
    """The person's Forgejo access token, refreshed first if it is about to
    expire. Nothing is locked while Forgejo is called: read and let go,
    refresh, then write back only if the stored token is still the one that was
    read.
    """
    key = settings.token_encryption_key_bytes
    tokens = await _token_columns(db, session_id)
    if not _is_due(tokens):
        return _decrypt(tokens.access, key)

    async with _lock_for(session_id):
        tokens = await _token_columns(db, session_id)
        if not _is_due(tokens):
            return _decrypt(tokens.access, key)
        issued = await _refreshed(db, settings, session_id, oidc, tokens.refresh)
        if await _store_tokens(db, settings, session_id, was=tokens.refresh, issued=issued):
            return issued.access_token
    return _decrypt((await _token_columns(db, session_id)).access, key)


async def revoke(db: AsyncSession, session_id: bytes, *, owner: int | None = None) -> None:
    """End one session. Given an `owner` it must be theirs; anyone else's is a
    404, because it is not theirs to see.
    """
    statement = _revocation().where(Session.id == session_id)
    if owner is not None:
        statement = statement.where(Session.user_id == owner)
    revoked = await db.execute(statement)
    await db.commit()
    if owner is not None and _rows_touched(revoked) == 0:
        raise NotFoundError("No such session.")


async def revoke_presented(db: AsyncSession, cookie: str | None) -> None:
    """End whatever session the browser is still carrying, if any."""
    if not cookie:
        return
    try:
        session_id = _id_of(cookie)
    except Unauthenticated:
        return
    await revoke(db, session_id)


async def revoke_all(db: AsyncSession, user_id: int) -> None:
    await db.execute(_revocation().where(Session.user_id == user_id))
    await db.commit()


async def list_for(
    db: AsyncSession, settings: Settings, session: ActiveSession
) -> list[SessionInfo]:
    now = datetime.now(UTC)
    rows = await db.execute(
        select(Session)
        .where(Session.user_id == session.user_id, Session.revoked_at.is_(None))
        .order_by(Session.created_at.desc())
    )
    return [
        SessionInfo(
            id=row.id.hex(),
            created_at=row.created_at,
            last_seen_at=row.last_seen_at,
            ip=str(row.ip) if row.ip else None,
            user_agent=row.user_agent,
            current=row.id == session.id,
        )
        for row in rows.scalars()
        if not is_expired(_times(row), now, settings.session_idle_ttl)
    ]


def _revocation() -> Update:
    """Revoked and disarmed in one statement, so a finished row never keeps a
    usable token. `coalesce` so revoking twice does not move the time it ended.
    """
    return update(Session).values(
        revoked_at=func.coalesce(Session.revoked_at, datetime.now(UTC)),
        forge_access_token=NO_TOKEN,
        forge_refresh_token=NO_TOKEN,
    )


def _rows_touched(result: Any) -> int:
    """`AsyncSession.execute` is typed as returning a plain `Result`; an UPDATE
    gives back the cursor result that counts rows.
    """
    cursor: CursorResult[Any] = result
    return cursor.rowcount


def _lock_for(session_id: bytes) -> asyncio.Lock:
    lock = _refreshing.get(session_id)
    if lock is None:
        lock = asyncio.Lock()
        _refreshing[session_id] = lock
    return lock


def _is_due(tokens: _Tokens) -> bool:
    return tokens.expires_at - datetime.now(UTC) <= REFRESH_MARGIN


async def _token_columns(db: AsyncSession, session_id: bytes) -> _Tokens:
    found = (
        await db.execute(
            select(
                Session.forge_access_token,
                Session.forge_refresh_token,
                Session.forge_token_expires_at,
                Session.revoked_at,
            ).where(Session.id == session_id)
        )
    ).one_or_none()
    await db.commit()
    if found is None or found.revoked_at is not None:
        raise Unauthenticated("No session.")
    return _Tokens(
        access=found.forge_access_token,
        refresh=found.forge_refresh_token,
        expires_at=found.forge_token_expires_at,
    )


async def _refreshed(
    db: AsyncSession, settings: Settings, session_id: bytes, oidc: Oidc, stored: bytes
) -> TokenSet:
    try:
        return await oidc.refresh(_decrypt(stored, settings.token_encryption_key_bytes))
    except ForgeTokenExpired as exc:
        log.info("session.forge_reauth", session=_short(session_id), reason=str(exc))
        await revoke(db, session_id)
        raise ForgeReauthRequired("Sign in again to keep working in the forge.") from exc
    except ForgeRejected:
        log.info("session.forge_misconfigured", session=_short(session_id))
        raise ForgeMisconfigured("The forge refused this instance.") from None


async def _store_tokens(
    db: AsyncSession, settings: Settings, session_id: bytes, *, was: bytes, issued: TokenSet
) -> bool:
    """Compare-and-set on the stored refresh token: whoever read it first gets to
    replace it.
    """
    key = settings.token_encryption_key_bytes
    written = await db.execute(
        update(Session)
        .where(Session.id == session_id, Session.forge_refresh_token == was)
        .values(
            forge_access_token=encrypt(issued.access_token, key),
            forge_refresh_token=encrypt(issued.refresh_token, key),
            forge_token_expires_at=issued.expires_at,
        )
    )
    await db.commit()
    return _rows_touched(written) == 1


def _short(session_id: bytes) -> str:
    """Enough of the row's key to follow one session through a log. It is a hash
    of the cookie, never the cookie.
    """
    return session_id.hex()[:12]


def _id_of(cookie: str) -> bytes:
    try:
        return session_id_for(cookie)
    except ValueError as exc:
        raise Unauthenticated("Malformed session cookie.") from exc


async def _row(db: AsyncSession, session_id: bytes) -> Session | None:
    query = select(Session).where(Session.id == session_id)
    return (await db.execute(query)).scalar_one_or_none()


def _times(row: Session) -> SessionTimes:
    return SessionTimes(
        expires_at=row.expires_at, last_seen_at=row.last_seen_at, revoked_at=row.revoked_at
    )


def _decrypt(blob: bytes, key: bytes) -> str:
    try:
        return decrypt(blob, key)
    except CannotDecrypt as exc:
        raise ForgeReauthRequired("Sign in again.") from exc
