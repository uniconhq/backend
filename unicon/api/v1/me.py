"""The signed-in person: who they are, what sessions they have, and the two ways
to end the account. Name, avatar and email come from Forgejo on every call, as
there is no users table to cache them in.
"""

from fastapi import APIRouter, Response, status

from unicon.api import cookies
from unicon.api.deps import AdminClientDep, Config, CurrentSession, Db, OidcClientDep
from unicon.domain.errors import NotFoundError
from unicon.schemas.account import Me, SessionInfo
from unicon.services import account, sessions

NO_CONTENT = status.HTTP_204_NO_CONTENT

router = APIRouter(prefix="/me", tags=["me"])


@router.get("", operation_id="getMe", summary="The signed-in person")
async def get_me(db: Db, settings: Config, session: CurrentSession, oidc: OidcClientDep) -> Me:
    return await account.me(db, settings, session, oidc)


@router.get("/sessions", operation_id="listMySessions", summary="This person's sessions")
async def list_my_sessions(db: Db, settings: Config, session: CurrentSession) -> list[SessionInfo]:
    return await sessions.list_for(db, settings, session)


@router.delete(
    "/sessions/{session_id}",
    operation_id="revokeMySession",
    summary="End one session",
    status_code=NO_CONTENT,
)
async def revoke_my_session(
    db: Db, settings: Config, session: CurrentSession, session_id: str
) -> Response:
    key = _key(session_id)
    await sessions.revoke(db, key, owner=session.user_id)
    if key == session.id:
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
    summary="Deactivate the forge account",
    status_code=NO_CONTENT,
)
async def deactivate_me(
    db: Db, settings: Config, session: CurrentSession, admin: AdminClientDep
) -> Response:
    await account.deactivate(db, settings, session, admin)
    return _signed_out(settings)


@router.delete(
    "", operation_id="deleteMe", summary="Delete the forge account", status_code=NO_CONTENT
)
async def delete_me(
    db: Db, settings: Config, session: CurrentSession, admin: AdminClientDep
) -> Response:
    await account.delete(db, settings, session, admin)
    return _signed_out(settings)


def _key(session_id: str) -> bytes:
    try:
        return bytes.fromhex(session_id)
    except ValueError as exc:
        raise NotFoundError("No such session.") from exc


def _signed_out(settings: Config) -> Response:
    response = Response(status_code=NO_CONTENT)
    cookies.clear_session(response, settings)
    return response
