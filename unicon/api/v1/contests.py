"""Making a contest in an org and listing the org's contests. Creating needs
the manager role at the org and makes the contest before it answers.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, status
from forge.api import contests
from forge.api.access import Organiser
from forge.api.types import Named as NamedRecord
from forge.api.types import OrgId, Role, ScopeKind

from unicon.api.guard import PREFIX, require
from unicon.schemas.contests import CreateContest, Named

CREATED = status.HTTP_201_CREATED
ORG = PREFIX[ScopeKind.ORG]

router = APIRouter(tags=["contests"])

OrgObserver = Annotated[Organiser, Depends(require(Role.OBSERVER))]
OrgManager = Annotated[Organiser, Depends(require(Role.MANAGER))]


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
    response_model=list[Named],
)
async def list_contests(organiser: OrgObserver) -> tuple[NamedRecord, ...]:
    """The contests the forge lets the caller read, by name."""
    return await contests.list(organiser, OrgId(organiser.scope.org))
