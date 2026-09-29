"""Making a contest in an org, listing the org's contests and following how
far making one has got. Creating needs the manager role at the org and
answers at once with the provisioning record; the poller makes the contest
in the background. Following it needs the observer role at the org, since
the contest may not be there yet to hold roles of its own.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, status
from forge.api import contests
from forge.api.access import Organiser
from forge.api.errors import NotFound
from forge.api.types import OrgName, Role, Scope, ScopeKind

from unicon.api.guard import PREFIX, require
from unicon.schemas.contests import Contest, CreateContest
from unicon.schemas.orgs import Provisioning

ACCEPTED = status.HTTP_202_ACCEPTED
ORG = PREFIX[ScopeKind.ORG]
CONTEST = PREFIX[ScopeKind.CONTEST]

router = APIRouter(tags=["contests"])

OrgObserver = Annotated[Organiser, Depends(require(Role.OBSERVER))]
OrgManager = Annotated[Organiser, Depends(require(Role.MANAGER))]


@router.post(
    f"{ORG}/contests",
    operation_id="createContest",
    summary="Ask for a contest to be made in the org",
    status_code=ACCEPTED,
)
async def create_contest(organiser: OrgManager, body: CreateContest) -> Provisioning:
    record = await contests.create(
        organiser, OrgName(organiser.scope.org), body.name, title=body.title
    )
    return Provisioning.of(record)


@router.get(f"{ORG}/contests", operation_id="listContests", summary="The org's contests")
async def list_contests(organiser: OrgObserver) -> list[Contest]:
    """The contests the forge lets the caller read, by name."""
    found = await contests.list(organiser, OrgName(organiser.scope.org))
    return [Contest.of(contest) for contest in found]


@router.get(
    f"{CONTEST}/provisioning",
    operation_id="getContestProvisioning",
    summary="How far making the contest has got",
)
async def get_contest_provisioning(organiser: OrgObserver, contest: str) -> Provisioning:
    """Not found when nothing has asked for the contest."""
    record = await contests.status(
        organiser, contests.contest_id_of(Scope(organiser.scope.org, contest))
    )
    if record is None:
        raise NotFound(f"Nothing has asked for a contest named {contest!r}.")
    return Provisioning.of(record)
