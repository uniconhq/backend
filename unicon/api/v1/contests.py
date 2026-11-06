"""Making a contest in an org, listing the org's contests and reading one,
each with its state and dates. Creating needs the manager role at the org
and makes the contest before it answers, the list needs the observer role
there, and reading one the observer role at the contest.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, status
from forge.api import contests
from forge.api.access import Organiser
from forge.api.contests import Listed
from forge.api.types import Named as NamedRecord
from forge.api.types import OrgId, Role, ScopeKind

from unicon.api.guard import PREFIX, require
from unicon.schemas.contests import CreateContest, ListedContest, Named

CREATED = status.HTTP_201_CREATED
ORG = PREFIX[ScopeKind.ORG]
CONTEST = PREFIX[ScopeKind.CONTEST]

router = APIRouter(tags=["contests"])

OrgObserver = Annotated[Organiser, Depends(require(Role.OBSERVER))]
OrgManager = Annotated[Organiser, Depends(require(Role.MANAGER))]
ContestObserver = Annotated[Organiser, Depends(require(Role.OBSERVER, ScopeKind.CONTEST))]


@router.post(
    f"{ORG}/contests",
    operation_id="createContest",
    summary="Make a contest in the org",
    status_code=CREATED,
    response_model=Named,
)
async def create_contest(organiser: OrgManager, body: CreateContest) -> NamedRecord:
    return await contests.create(organiser, OrgId(organiser.scope.org), body.name, title=body.title)


@router.get(
    f"{ORG}/contests",
    operation_id="listContests",
    summary="The org's contests",
    response_model=list[ListedContest],
)
async def list_contests(organiser: OrgObserver) -> tuple[Listed, ...]:
    """The contests the forge lets the caller read, by name, each with its
    state and dates and what the caller may do there.
    """
    return await contests.list_contests(organiser, OrgId(organiser.scope.org))


@router.get(
    CONTEST,
    operation_id="getContest",
    summary="The contest, as the org's list tells it",
    response_model=ListedContest,
)
async def get_contest(organiser: ContestObserver) -> Listed:
    """The contest's state and dates, null when its settings do not read,
    and what the caller may do there.
    """
    return await contests.read(organiser, contests.contest_id_of(organiser.scope))
