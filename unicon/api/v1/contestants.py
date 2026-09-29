"""Registering for a contest and the organisers' decisions on it. The caller
registers themself and reads their own registration with a session and no
role. Listing a contest's registrations needs the observer role at the
contest, and approving, rejecting, removing and giving someone more time need
the manager role there. Forge checks the contest's rules and each decision,
and every refusal comes back with its own code.
"""

from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, status
from forge.api import contestants, contests
from forge.api.access import Organiser
from forge.api.types import ContestId, Role, ScopeKind

from unicon.api.deps import CurrentSession
from unicon.api.guard import PREFIX, ContestAtPath, require
from unicon.schemas.contestants import (
    Contestant,
    ExtensionRequest,
    MyRegistration,
    RegisterRequest,
    RejectRequest,
)

CREATED = status.HTTP_201_CREATED
CONTEST = PREFIX[ScopeKind.CONTEST]

router = APIRouter(tags=["contestants"])

ContestObserver = Annotated[Organiser, Depends(require(Role.OBSERVER, ScopeKind.CONTEST))]
ContestManager = Annotated[Organiser, Depends(require(Role.MANAGER, ScopeKind.CONTEST))]


def _contest(organiser: Organiser) -> ContestId:
    """The contest the guard checked the organiser at."""
    return contests.contest_id_of(organiser.scope)


@router.post(
    f"{CONTEST}/registration",
    operation_id="registerForContest",
    summary="Register the caller for the contest",
    status_code=CREATED,
)
async def register(
    session: CurrentSession, scope: ContestAtPath, body: RegisterRequest
) -> MyRegistration:
    """Pending until an organiser decides it, or approved at once when the
    contest approves on its own. A registration the contest's rules refuse
    comes back with the rule's code, such as `registration_closed` or
    `contest_full`.
    """
    registration = await contestants.register(
        session, contests.contest_id_of(scope), invite_code=body.invite_code
    )
    return MyRegistration.of(registration)


@router.get(
    f"{CONTEST}/registration",
    operation_id="getMyRegistration",
    summary="The caller's own registration for the contest",
)
async def get_my_registration(
    session: CurrentSession, scope: ContestAtPath
) -> MyRegistration | None:
    """Null when the caller has not registered."""
    registration = await contestants.mine(session, contests.contest_id_of(scope))
    return MyRegistration.of(registration) if registration is not None else None


@router.get(
    f"{CONTEST}/contestants",
    operation_id="listContestants",
    summary="Every registration for the contest",
)
async def list_contestants(organiser: ContestObserver) -> list[Contestant]:
    """Oldest first, each with where an approved contestant's workspace
    stands.
    """
    found = await contestants.list(organiser, _contest(organiser))
    return [Contestant.of(registration) for registration in found]


@router.post(
    f"{CONTEST}/contestants/{{user_id}}/approve",
    operation_id="approveContestant",
    summary="Approve a pending registration",
)
async def approve_contestant(organiser: ContestManager, user_id: int) -> Contestant:
    """The contestant's workspace starts being made at once."""
    return Contestant.of(await contestants.approve(organiser, _contest(organiser), user_id))


@router.post(
    f"{CONTEST}/contestants/{{user_id}}/reject",
    operation_id="rejectContestant",
    summary="Reject a pending registration with a reason",
)
async def reject_contestant(
    organiser: ContestManager, user_id: int, body: RejectRequest
) -> Contestant:
    """The person reads the reason on their own page."""
    return Contestant.of(
        await contestants.reject(organiser, _contest(organiser), user_id, body.reason)
    )


@router.post(
    f"{CONTEST}/contestants/{{user_id}}/remove",
    operation_id="removeContestant",
    summary="Remove an approved contestant",
)
async def remove_contestant(organiser: ContestManager, user_id: int) -> Contestant:
    """They can no longer write their workspace, and what is in it stays."""
    return Contestant.of(await contestants.remove(organiser, _contest(organiser), user_id))


@router.put(
    f"{CONTEST}/contestants/{{user_id}}/extension",
    operation_id="extendContestant",
    summary="Give one person more time past the contest's end",
)
async def extend_contestant(
    organiser: ContestManager, user_id: int, body: ExtensionRequest
) -> Contestant:
    """In place of any extension they had; zero takes it away."""
    return Contestant.of(
        await contestants.extend(
            organiser, _contest(organiser), user_id, timedelta(seconds=body.seconds)
        )
    )
