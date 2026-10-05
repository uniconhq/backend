"""Invites. An organiser makes, lists, sends again and withdraws the invites
of a scope, under each kind of scope, made by `router_at`, so each kind gets
its own operation names in the document: listing needs the observer role
there and the rest manager, and forge refuses a manager inviting an admin.
The signed-in person lists their own pending invites, opens one by the token
its mail carried, and accepts or declines it with a session alone, since an
invite is addressed to them and to nobody else; forge answers anyone else's
as no such invite. Every refusal comes back with its code.
"""

import uuid
from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, status
from forge.api import invites
from forge.api.access import Organiser
from forge.api.types import Role, ScopeKind

from unicon.api.deps import CurrentSession
from unicon.api.guard import PREFIX, require
from unicon.schemas.invites import Invite, InviteRequest, OpenInviteRequest

CREATED = status.HTTP_201_CREATED


def router_at(kind: ScopeKind) -> APIRouter:
    """The organiser's invite routes under the prefix of `kind`."""
    name = kind.value.capitalize()
    router = APIRouter(prefix=PREFIX[kind], tags=["invites"])
    Observer = Annotated[Organiser, Depends(require(Role.OBSERVER, kind))]
    Manager = Annotated[Organiser, Depends(require(Role.MANAGER, kind))]

    @router.get(
        "/invites",
        operation_id=f"list{name}Invites",
        summary=f"The invites made at the {kind.value}",
        response_model=list[Invite],
    )
    async def list_invites(organiser: Observer) -> tuple[invites.Invite, ...]:
        """Newest first, whatever became of each."""
        return await invites.at(organiser, organiser.scope)

    @router.post(
        "/invites",
        operation_id=f"create{name}Invite",
        summary=f"Invite someone to the {kind.value}",
        status_code=CREATED,
        response_model=Invite,
    )
    async def create_invite(organiser: Manager, body: InviteRequest) -> invites.Invite:
        """By username or by email address, to an organiser role here, or to
        a contestant's place at a contest. The mail goes out after the answer.
        """
        return await invites.create(
            organiser,
            organiser.scope,
            body.grants,
            username=body.username,
            email=body.email,
            lifetime=timedelta(days=body.days) if body.days is not None else None,
        )

    @router.post(
        "/invites/{invite_id}/send-again",
        operation_id=f"send{name}InviteAgain",
        summary="Mail a pending invite again, with a new link",
        response_model=Invite,
    )
    async def send_invite_again(organiser: Manager, invite_id: uuid.UUID) -> invites.Invite:
        """The link the earlier mail carried stops working."""
        return await invites.send_again(organiser, organiser.scope, invite_id)

    @router.post(
        "/invites/{invite_id}/withdraw",
        operation_id=f"withdraw{name}Invite",
        summary="Take a pending invite back",
        response_model=Invite,
    )
    async def withdraw_invite(organiser: Manager, invite_id: uuid.UUID) -> invites.Invite:
        return await invites.withdraw(organiser, organiser.scope, invite_id)

    return router


mine = APIRouter(prefix="/me/invites", tags=["invites"])


@mine.get(
    "",
    operation_id="listMyInvites",
    summary="The invites waiting for the signed-in user",
    response_model=list[Invite],
)
async def list_my_invites(session: CurrentSession) -> tuple[invites.Invite, ...]:
    """Pending ones, lapsed ones flagged, including any sent to an address the
    forge has confirmed is theirs.
    """
    return await invites.mine(session)


@mine.post(
    "/open",
    operation_id="openMyInvite",
    summary="The invite an invite mail's link carries",
    response_model=Invite,
)
async def open_my_invite(session: CurrentSession, body: OpenInviteRequest) -> invites.Invite:
    """Only the person the invite is for opens it; for anyone else it is no
    such invite. Sent in the body so the token never sits in a URL.
    """
    return await invites.by_token(session, body.token)


@mine.post(
    "/{invite_id}/accept",
    operation_id="acceptMyInvite",
    summary="Accept an invite and take what it grants",
    response_model=Invite,
)
async def accept_my_invite(session: CurrentSession, invite_id: uuid.UUID) -> invites.Invite:
    return await invites.accept(session, invite_id)


@mine.post(
    "/{invite_id}/decline",
    operation_id="declineMyInvite",
    summary="Decline an invite",
    response_model=Invite,
)
async def decline_my_invite(session: CurrentSession, invite_id: uuid.UUID) -> invites.Invite:
    return await invites.decline(session, invite_id)
