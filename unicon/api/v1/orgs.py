"""Making an org, and what its admin changes about it afterwards. Creating
makes the org before it answers, and the caller is its first admin from
then on. Whether anyone signed in may create an org is the deployment's
setting, and forge refuses when it is off.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from forge.api import orgs
from forge.api.access import Organiser
from forge.api.types import Named as NamedRecord
from forge.api.types import OrgId, Role, ScopeKind

from unicon.api.deps import CurrentSession
from unicon.api.guard import PREFIX, require
from unicon.schemas.contests import Named
from unicon.schemas.orgs import CreateOrg, UpdateOrg

CREATED = status.HTTP_201_CREATED
NO_CONTENT = status.HTTP_204_NO_CONTENT

ORG = PREFIX[ScopeKind.ORG]

router = APIRouter(tags=["orgs"])


@router.post(
    "/orgs",
    operation_id="createOrg",
    summary="Make an org",
    status_code=CREATED,
    response_model=Named,
)
async def create_org(session: CurrentSession, body: CreateOrg) -> NamedRecord:
    """The caller becomes the org's first admin."""
    return await orgs.create(session, body.name, description=body.description)


@router.patch(
    ORG,
    operation_id="updateOrg",
    summary="Change the org's description and display name",
    status_code=NO_CONTENT,
)
async def update_org(
    organiser: Annotated[Organiser, Depends(require(Role.ADMIN))], body: UpdateOrg
) -> Response:
    await orgs.update(
        organiser,
        OrgId(organiser.scope.org),
        description=body.description,
        display_name=body.display_name,
    )
    return Response(status_code=NO_CONTENT)
