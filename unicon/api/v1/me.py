"""The signed-in user: who they are and their roles, where they are signed
in, and the two ways to leave. Each route calls the package and returns its
refusal unchanged.
"""

import uuid

from fastapi import APIRouter, Response, status
from forge.domain.errors import NotFound
from forge.services import account, identity, sessions

from unicon.api import cookies
from unicon.api.deps import Config, Ctx, CurrentSession
from unicon.schemas.account import Me, SessionInfo
from unicon.settings import ShellSettings

NO_CONTENT = status.HTTP_204_NO_CONTENT

router = APIRouter(prefix="/me", tags=["me"])


@router.get("", operation_id="getMe", summary="The signed-in user and their roles")
async def get_me(ctx: Ctx, session: CurrentSession) -> Me:
    return Me.of(await identity.whoami(ctx, session))


@router.get("/sessions", operation_id="listMySessions", summary="Where this user is signed in")
async def list_my_sessions(ctx: Ctx, session: CurrentSession) -> list[SessionInfo]:
    return [SessionInfo.of(info) for info in await sessions.list_for(ctx, session)]


@router.delete(
    "/sessions/{session_id}",
    operation_id="revokeMySession",
    summary="End one session",
    status_code=NO_CONTENT,
)
async def revoke_my_session(
    settings: Config, ctx: Ctx, session: CurrentSession, session_id: str
) -> Response:
    target = _session_id(session_id)
    await sessions.revoke(ctx, target, owner=session.user_id)
    if target == session.id:
        return _signed_out(settings)
    return Response(status_code=NO_CONTENT)


@router.delete(
    "/sessions",
    operation_id="revokeAllMySessions",
    summary="Sign out everywhere, including here",
    status_code=NO_CONTENT,
)
async def revoke_all_my_sessions(settings: Config, ctx: Ctx, session: CurrentSession) -> Response:
    await sessions.revoke_all(ctx, session.user_id)
    return _signed_out(settings)


@router.post(
    "/deactivate",
    operation_id="deactivateMe",
    summary="Deactivate the account at the forge",
    status_code=NO_CONTENT,
)
async def deactivate_me(settings: Config, ctx: Ctx, session: CurrentSession) -> Response:
    await account.deactivate(ctx, session)
    return _signed_out(settings)


@router.delete(
    "", operation_id="deleteMe", summary="Delete the account at the forge", status_code=NO_CONTENT
)
async def delete_me(settings: Config, ctx: Ctx, session: CurrentSession) -> Response:
    await account.delete(ctx, session)
    return _signed_out(settings)


def _session_id(value: str) -> uuid.UUID:
    try:
        return uuid.UUID(hex=value)
    except ValueError as exc:
        raise NotFound("No such session.") from exc


def _signed_out(settings: ShellSettings) -> Response:
    response = Response(status_code=NO_CONTENT)
    cookies.clear_session(response, settings)
    return response
