"""Registering for a contest and the organisers' decisions on it. The caller
registers themself and reads their own registration with a session and no
role. Listing a contest's registrations needs the observer role at the
contest, and approving, rejecting, taking a rejection back, removing and
giving someone more time need the manager role there. Forge checks the
contest's rules and each decision, and every refusal comes back with its own
code.
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
    response_model=MyRegistration,
)
async def register(
    session: CurrentSession, scope: ContestAtPath, body: RegisterRequest
) -> contestants.Registration:
    """Pending until an organiser decides it, or approved at once when the
    contest approves on its own. A registration the contest's rules refuse
    comes back with the rule's code, such as `registration_closed` or
    `contest_full`.
    """
    return await contestants.register(
        session, contests.contest_id_of(scope), invite_code=body.invite_code
    )


@router.get(
    f"{CONTEST}/registration",
    operation_id="getMyRegistration",
    summary="The caller's own registration for the contest",
    response_model=MyRegistration | None,
)
async def get_my_registration(
    session: CurrentSession, scope: ContestAtPath
) -> contestants.Registration | None:
    """Null when the caller has not registered."""
    return await contestants.mine(session, contests.contest_id_of(scope))


@router.get(
    f"{CONTEST}/contestants",
    operation_id="listContestants",
    summary="Every registration for the contest",
    response_model=list[Contestant],
)
async def list_contestants(organiser: ContestObserver) -> tuple[contestants.Registration, ...]:
    """Oldest first, each with where an approved contestant's workspace
    stands.
    """
    return await contestants.list(organiser, _contest(organiser))


@router.post(
    f"{CONTEST}/contestants/{{user_id}}/approve",
    operation_id="approveContestant",
    summary="Approve a pending registration",
    response_model=Contestant,
)
async def approve_contestant(organiser: ContestManager, user_id: int) -> contestants.Registration:
    """The contestant's workspace starts being made at once."""
    return await contestants.approve(organiser, _contest(organiser), user_id)


@router.post(
    f"{CONTEST}/contestants/{{user_id}}/reject",
    operation_id="rejectContestant",
    summary="Reject a pending registration with a reason",
    response_model=Contestant,
)
async def reject_contestant(
    organiser: ContestManager, user_id: int, body: RejectRequest
) -> contestants.Registration:
    """The person reads the reason on their own page."""
    return await contestants.reject(organiser, _contest(organiser), user_id, body.reason)


@router.post(
    f"{CONTEST}/contestants/{{user_id}}/reopen",
    operation_id="reopenContestant",
    summary="Take a rejection back, leaving the registration pending",
    response_model=Contestant,
)
async def reopen_contestant(organiser: ContestManager, user_id: int) -> contestants.Registration:
    """The reason goes, and the registration waits for a decision again. It
    takes a place again, so a full contest refuses it with `contest_full`, and
    someone who holds a role at the contest by now with `is_staff`.
    """
    return await contestants.reopen(organiser, _contest(organiser), user_id)


@router.post(
    f"{CONTEST}/contestants/{{user_id}}/remove",
    operation_id="removeContestant",
    summary="Remove an approved contestant",
    response_model=Contestant,
)
async def remove_contestant(organiser: ContestManager, user_id: int) -> contestants.Registration:
    """They can no longer write their workspace, and what is in it stays."""
    return await contestants.remove(organiser, _contest(organiser), user_id)


@router.put(
    f"{CONTEST}/contestants/{{user_id}}/extension",
    operation_id="extendContestant",
    summary="Give one person more time on the contest's tasks",
    response_model=Contestant,
)
async def extend_contestant(
    organiser: ContestManager, user_id: int, body: ExtensionRequest
) -> contestants.Registration:
    """It moves their due and close on the named tasks, or on every task
    when none are named, in place of any extension they had; zero takes it
    away. It holds while they work alone; in a team, the team's holds. One
    that names a task the contest does not list, would let them submit to
    a task whose reveal has passed, or would leave one of their submissions
    after the due or the close it was made before is `invalid_extension`.
    """
    return await contestants.extend(
        organiser,
        _contest(organiser),
        user_id,
        timedelta(seconds=body.seconds),
        tasks=body.tasks,
    )
