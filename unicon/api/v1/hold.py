"""Where the contest's hold stands, and a manager ending it early."""

from typing import Annotated

from fastapi import APIRouter, Depends
from forge.api import contests, hold
from forge.api.access import Organiser
from forge.api.types import Role, ScopeKind

from unicon.api.guard import PREFIX, require
from unicon.schemas.hold import HoldRequest, HoldState

router = APIRouter(tags=["hold"])

CONTEST = PREFIX[ScopeKind.CONTEST]
ContestObserver = Annotated[Organiser, Depends(require(Role.OBSERVER, ScopeKind.CONTEST))]
ContestManager = Annotated[Organiser, Depends(require(Role.MANAGER, ScopeKind.CONTEST))]


@router.get(
    f"{CONTEST}/hold",
    operation_id="getHold",
    summary="Where the contest's hold stands",
    response_model=HoldState,
)
async def get_hold(organiser: ContestObserver) -> hold.HoldState:
    """Its `from` and `until`, whether it holds now, and who ended it early
    and when, if anyone did."""
    return await hold.hold_state(organiser, contests.contest_id_of(organiser.scope))


@router.post(
    f"{CONTEST}/hold/end",
    operation_id="endHold",
    summary="End the contest's hold early",
    response_model=HoldState,
)
async def end_hold(organiser: ContestManager, body: HoldRequest) -> hold.HoldState:
    """From now on every caller reads every row as it stands. Without
    `confirm`, nothing changes and the answer is `confirmation_required`
    with `action` `end_hold` and, as its detail, what becomes visible and
    that this hold cannot be put back. A hold already ended, early or at
    its `until`, or not started yet, answers as it stands; a contest with
    no hold is `not_found`. The answer is read once the end has landed.
    """
    contest = contests.contest_id_of(organiser.scope)
    await hold.end_hold(organiser, contest, confirmed=body.confirm)
    return await hold.hold_state(organiser, contest)
