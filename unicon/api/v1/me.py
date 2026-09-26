"""The signed-in user: who they are and their roles, where they are signed
in, and the two ways to leave. Each route calls the package and returns its
refusal unchanged.
"""

import uuid

from fastapi import APIRouter, Response, status
from forge.domain.errors import NotFound
from forge.services import account, identity, sessions

from unicon.api import cookies
from unicon.api.deps import Config, CurrentSession, Db, ForgeDep
from unicon.schemas.account import Me, SessionInfo

NO_CONTENT = status.HTTP_204_NO_CONTENT

router = APIRouter(prefix="/me", tags=["me"])


@router.get("", operation_id="getMe", summary="The signed-in user and their roles")
async def get_me(db: Db, settings: Config, forge: ForgeDep, session: CurrentSession) -> Me:
    return Me.of(await identity.whoami(db, settings, forge, session))


@router.get("/sessions", operation_id="listMySessions", summary="Where this user is signed in")
async def list_my_sessions(db: Db, settings: Config, session: CurrentSession) -> list[SessionInfo]:
    return [SessionInfo.of(info) for info in await sessions.list_for(db, settings, session)]


@router.delete(
    "/sessions/{session_id}",
    operation_id="revokeMySession",
    summary="End one session",
    status_code=NO_CONTENT,
)
async def revoke_my_session(
    db: Db, settings: Config, session: CurrentSession, session_id: str
) -> Response:
    target = _session_id(session_id)
    await sessions.revoke(db, target, owner=session.user_id)
    if target == session.id:
        return _signed_out(settings)
    return Response(status_code=NO_CONTENT)


@router.delete(
    "/sessions",
    operation_id="revokeAllMySessions",
    summary="Sign out everywhere, including here",
    status_code=NO_CONTENT,
)
async def revoke_all_my_sessions(db: Db, settings: Config, session: CurrentSession) -> Response:
    await sessions.revoke_all(db, session.user_id)
    return _signed_out(settings)


@router.post(
    "/deactivate",
    operation_id="deactivateMe",
    summary="Deactivate the account at the forge",
    status_code=NO_CONTENT,
)
async def deactivate_me(
    db: Db, settings: Config, forge: ForgeDep, session: CurrentSession
) -> Response:
    await account.deactivate(db, settings, forge, session)
    return _signed_out(settings)


@router.delete(
    "", operation_id="deleteMe", summary="Delete the account at the forge", status_code=NO_CONTENT
)
async def delete_me(db: Db, settings: Config, forge: ForgeDep, session: CurrentSession) -> Response:
    await account.delete(db, settings, forge, session)
    return _signed_out(settings)


def _session_id(value: str) -> uuid.UUID:
    try:
        return uuid.UUID(hex=value)
    except ValueError as exc:
        raise NotFound("No such session.") from exc


def _signed_out(settings: Config) -> Response:
    response = Response(status_code=NO_CONTENT)
    cookies.clear_session(response, settings)
    return response
