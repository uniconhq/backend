"""Entrants: the one kind of entry a contest has, one or more people who enter
together. The caller registers a new entrant, reads their registration
panel, invites people into their entrant and withdraws those invites, leaves
it and renames it with a session and no role, since forge checks they are in
it and that its roster is still open. The contest's organisers list every
entrant with the observer role at the contest, and approve, reject, take a
rejection back, remove, extend, rename, take a member out, move one to
another entrant and delete an entrant with manager, whatever the roster's
lock. Joining an entrant is accepting an invite (`/me/invites`). Every
refusal comes back with forge's code, such as `contest_full`,
`roster_locked`, `entrant_full` or `entrant_incomplete`.
"""

import uuid
from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from forge.api import contests, entrants, invites
from forge.api.access import Organiser
from forge.api.types import ContestId, Role, ScopeKind

from unicon.api.deps import CurrentSession
from unicon.api.guard import PREFIX, ContestAtPath, require
from unicon.schemas.entrants import (
    Entrant,
    ExtensionRequest,
    MemberInviteRequest,
    MoveRequest,
    MyEntry,
    NameRequest,
    OrganisedEntrant,
    RegisterRequest,
    RejectRequest,
)
from unicon.schemas.invites import Invite

CREATED = status.HTTP_201_CREATED
NO_CONTENT = status.HTTP_204_NO_CONTENT
CONTEST = PREFIX[ScopeKind.CONTEST]
MINE = f"{CONTEST}/entrants/mine"
ORGANISE = f"{CONTEST}/organise/entrants"
ONE = f"{ORGANISE}/{{entrant_id}}"

router = APIRouter(tags=["entrants"])

ContestObserver = Annotated[Organiser, Depends(require(Role.OBSERVER, ScopeKind.CONTEST))]
ContestManager = Annotated[Organiser, Depends(require(Role.MANAGER, ScopeKind.CONTEST))]


def _contest(organiser: Organiser) -> ContestId:
    """The contest the guard checked the organiser at."""
    return contests.contest_id_of(organiser.scope)


# The caller's own entrant.


@router.post(
    f"{CONTEST}/entrants",
    operation_id="registerEntrant",
    summary="Register a new entrant with the caller as its first member",
    status_code=CREATED,
    response_model=Entrant,
)
async def register(
    session: CurrentSession, scope: ContestAtPath, body: RegisterRequest
) -> entrants.Entrant:
    """Pending until an organiser decides it, or approved at once when it is
    complete and the caller came in by a way that approves straight away. A
    registration the contest's rules refuse comes back with the rule's code,
    such as `registration_closed`, `wrong_invite_code` or `contest_full`.
    """
    return await entrants.register(
        session, contests.contest_id_of(scope), name=body.name, code=body.code
    )


@router.get(
    MINE,
    operation_id="getMyEntry",
    summary="The caller's registration panel for the contest",
    response_model=MyEntry,
)
async def get_mine(session: CurrentSession, scope: ContestAtPath) -> entrants.Mine:
    """Their entrant, null when they are in none, their invites into the
    contest's entrants, and whether and how they may register.
    """
    return await entrants.mine(session, contests.contest_id_of(scope))


@router.post(
    f"{MINE}/invites",
    operation_id="inviteIntoMyEntrant",
    summary="Ask someone into the caller's entrant",
    status_code=CREATED,
    response_model=Invite,
)
async def invite_into_mine(
    session: CurrentSession, scope: ContestAtPath, body: MemberInviteRequest
) -> invites.Invite:
    """By username or by email address; the mail goes out after the answer.
    The members and the invites waiting count against the contest's most.
    """
    return await entrants.invite(
        session, contests.contest_id_of(scope), username=body.username, email=body.email
    )


@router.delete(
    f"{MINE}/invites/{{invite_id}}",
    operation_id="withdrawMyEntrantsInvite",
    summary="Take back an invite into the caller's entrant",
    response_model=Invite,
)
async def withdraw_from_mine(
    session: CurrentSession, scope: ContestAtPath, invite_id: uuid.UUID
) -> invites.Invite:
    return await entrants.withdraw_invite(session, contests.contest_id_of(scope), invite_id)


@router.post(
    f"{MINE}/leave",
    operation_id="leaveMyEntrant",
    summary="Leave the caller's entrant",
    status_code=NO_CONTENT,
)
async def leave_mine(session: CurrentSession, scope: ContestAtPath) -> Response:
    """Before its roster locks. Access to its workspace goes; what it made
    stays its own, and one left with nobody and no submissions goes.
    """
    await entrants.leave(session, contests.contest_id_of(scope))
    return Response(status_code=NO_CONTENT)


@router.put(
    f"{MINE}/name",
    operation_id="renameMyEntrant",
    summary="Rename the caller's entrant",
    response_model=Entrant,
)
async def rename_mine(
    session: CurrentSession, scope: ContestAtPath, body: NameRequest
) -> entrants.Entrant:
    return await entrants.rename(session, contests.contest_id_of(scope), body.name)


# The organisers'.


@router.get(
    ORGANISE,
    operation_id="listEntrants",
    summary="Every entrant of the contest",
    response_model=list[OrganisedEntrant],
)
async def list_entrants(organiser: ContestObserver) -> tuple[entrants.Entrant, ...]:
    """The earliest registered first, each with its members and the way
    each came in by.
    """
    return await entrants.list_entrants(organiser, _contest(organiser))


@router.post(
    f"{ONE}/approve",
    operation_id="approveEntrant",
    summary="Approve a pending entrant",
    response_model=OrganisedEntrant,
)
async def approve(organiser: ContestManager, entrant_id: uuid.UUID) -> entrants.Entrant:
    """Refused as `entrant_incomplete` while it has fewer members than the
    contest asks. Its workspace starts being made at once.
    """
    return await entrants.approve(organiser, _contest(organiser), entrant_id)


@router.post(
    f"{ONE}/reject",
    operation_id="rejectEntrant",
    summary="Reject a pending entrant with a reason",
    response_model=OrganisedEntrant,
)
async def reject(
    organiser: ContestManager, entrant_id: uuid.UUID, body: RejectRequest
) -> entrants.Entrant:
    """Its members read the reason on their own page."""
    return await entrants.reject(organiser, _contest(organiser), entrant_id, body.reason)


@router.post(
    f"{ONE}/reopen",
    operation_id="reopenEntrant",
    summary="Take a rejection back, leaving the entrant pending",
    response_model=OrganisedEntrant,
)
async def reopen(organiser: ContestManager, entrant_id: uuid.UUID) -> entrants.Entrant:
    """The reason goes, and the entrant waits for a decision again. It takes
    a place again, so a full contest refuses it with `contest_full`, and a
    member who holds a role at the contest by now with `is_staff`.
    """
    return await entrants.reopen(organiser, _contest(organiser), entrant_id)


@router.post(
    f"{ONE}/remove",
    operation_id="removeEntrant",
    summary="Remove an approved entrant",
    response_model=OrganisedEntrant,
)
async def remove(organiser: ContestManager, entrant_id: uuid.UUID) -> entrants.Entrant:
    """Its members can no longer write its workspace, and what is in it
    stays.
    """
    return await entrants.remove(organiser, _contest(organiser), entrant_id)


@router.put(
    f"{ONE}/extension",
    operation_id="extendEntrant",
    summary="Give an entrant more time on the contest's tasks",
    response_model=OrganisedEntrant,
)
async def extend(
    organiser: ContestManager, entrant_id: uuid.UUID, body: ExtensionRequest
) -> entrants.Entrant:
    """It moves the entrant's due and close on the named tasks, or on every
    task when none are named, in place of any extension it had; zero takes
    it away. One that names a task the contest does not list, would let it
    submit to a task whose reveal has passed, or would leave one of its
    submissions after the due or the close it was made before is
    `invalid_extension`.
    """
    return await entrants.extend(
        organiser,
        _contest(organiser),
        entrant_id,
        timedelta(seconds=body.seconds),
        tasks=body.tasks,
    )


@router.put(
    f"{ONE}/name",
    operation_id="renameEntrant",
    summary="Rename an entrant",
    response_model=OrganisedEntrant,
)
async def rename(
    organiser: ContestManager, entrant_id: uuid.UUID, body: NameRequest
) -> entrants.Entrant:
    return await entrants.organise_rename(organiser, _contest(organiser), entrant_id, body.name)


@router.delete(
    ONE,
    operation_id="deleteEntrant",
    summary="Delete an entrant that has submitted nothing",
    status_code=NO_CONTENT,
)
async def delete(organiser: ContestManager, entrant_id: uuid.UUID) -> Response:
    """Every member's access to its workspace goes, and the invites into it
    are withdrawn; one that has submitted is `entrant_has_submissions`.
    """
    await entrants.delete(organiser, _contest(organiser), entrant_id)
    return Response(status_code=NO_CONTENT)


@router.delete(
    f"{ONE}/members/{{user_id}}",
    operation_id="removeEntrantMember",
    summary="Take someone out of an entrant",
    response_model=OrganisedEntrant | None,
)
async def remove_member(
    organiser: ContestManager, entrant_id: uuid.UUID, user_id: int
) -> entrants.Entrant | None:
    """Their access to its workspace goes. Null when that leaves the entrant
    with nobody and no submissions, which goes too.
    """
    return await entrants.remove_member(organiser, _contest(organiser), entrant_id, user_id)


@router.post(
    f"{ONE}/members/{{user_id}}/move",
    operation_id="moveEntrantMember",
    summary="Move someone to another entrant of the contest",
    response_model=OrganisedEntrant,
)
async def move_member(
    organiser: ContestManager, entrant_id: uuid.UUID, user_id: int, body: MoveRequest
) -> entrants.Entrant:
    """Answers with the entrant they are in now. Refused as `entrant_full`
    when it has no room, and as `entrant_has_submissions` for the last
    member of an entrant that has submitted, whose results would have
    nobody.
    """
    return await entrants.move_member(organiser, _contest(organiser), entrant_id, user_id, body.to)
