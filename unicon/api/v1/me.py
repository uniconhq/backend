"""The signed-in user: who they are and their roles, where they are signed
in, and the two ways to leave. Each route calls one forge action and returns
its refusal unchanged.
"""

import uuid

from fastapi import APIRouter, Response, status
from forge.api import account, identity, sessions
from forge.api.errors import NotFound

from unicon.api import cookies
from unicon.api.deps import CurrentSession
from unicon.schemas.account import Me, SessionInfo

NO_CONTENT = status.HTTP_204_NO_CONTENT

router = APIRouter(prefix="/me", tags=["me"])


@router.get("", operation_id="getMe", summary="The signed-in user and their roles")
async def get_me(session: CurrentSession) -> Me:
    return Me.of(await identity.whoami(session))


@router.get("/sessions", operation_id="listMySessions", summary="Where this user is signed in")
async def list_my_sessions(session: CurrentSession) -> list[SessionInfo]:
    return [SessionInfo.of(info) for info in await sessions.list_for(session)]


@router.delete(
    "/sessions/{session_id}",
    operation_id="revokeMySession",
    summary="End one session",
    status_code=NO_CONTENT,
)
async def revoke_my_session(session: CurrentSession, session_id: str) -> Response:
    target = _session_id(session_id)
    await sessions.revoke(target, owner=session.user_id)
    if target == session.id:
        return _signed_out()
    return Response(status_code=NO_CONTENT)


@router.delete(
    "/sessions",
    operation_id="revokeAllMySessions",
    summary="Sign out everywhere, including here",
    status_code=NO_CONTENT,
)
async def revoke_all_my_sessions(session: CurrentSession) -> Response:
    await sessions.revoke_all(session.user_id)
    return _signed_out()


@router.post(
    "/deactivate",
    operation_id="deactivateMe",
    summary="Deactivate the account at the forge",
    status_code=NO_CONTENT,
)
async def deactivate_me(session: CurrentSession) -> Response:
    await account.deactivate(session)
    return _signed_out()


@router.delete(
    "", operation_id="deleteMe", summary="Delete the account at the forge", status_code=NO_CONTENT
)
async def delete_me(session: CurrentSession) -> Response:
    await account.delete(session)
    return _signed_out()


def _session_id(value: str) -> uuid.UUID:
    try:
        return uuid.UUID(hex=value)
    except ValueError as exc:
        raise NotFound("No such session.") from exc


def _signed_out() -> Response:
    response = Response(status_code=NO_CONTENT)
    cookies.clear_session(response)
    return response
