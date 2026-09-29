"""Making an org and following it to ready, and what its admin changes
about it afterwards. Creating answers at once with the provisioning record,
since the forge work runs in the background; the status route is for the
person who asked, who is not yet an organiser of anything while the org is
being made. Whether anyone signed in may create an org is the deployment's
setting, and forge refuses when it is off.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from forge.api import orgs
from forge.api.access import Organiser
from forge.api.errors import NotFound
from forge.api.types import OrgName, Role, ScopeKind

from unicon.api.deps import CurrentSession
from unicon.api.guard import PREFIX, require
from unicon.schemas.orgs import CreateOrg, Provisioning, UpdateOrg

ACCEPTED = status.HTTP_202_ACCEPTED
NO_CONTENT = status.HTTP_204_NO_CONTENT

ORG = PREFIX[ScopeKind.ORG]

router = APIRouter(tags=["orgs"])


@router.post(
    "/orgs", operation_id="createOrg", summary="Ask for an org to be made", status_code=ACCEPTED
)
async def create_org(session: CurrentSession, body: CreateOrg) -> Provisioning:
    """The caller becomes the org's first admin once it is ready."""
    record = await orgs.create(session, OrgName(body.name), description=body.description)
    return Provisioning.of(record)


@router.get(
    f"{ORG}/provisioning",
    operation_id="getOrgProvisioning",
    summary="How far making the org has got",
)
async def get_org_provisioning(session: CurrentSession, org: str) -> Provisioning:
    """Not found when nothing was asked for under that name, or someone else
    asked for it.
    """
    record = await orgs.status(session, OrgName(org))
    if record is None:
        raise NotFound(f"You have not asked for an org named {org!r}.")
    return Provisioning.of(record)


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
        OrgName(organiser.scope.org),
        description=body.description,
        display_name=body.display_name,
    )
    return Response(status_code=NO_CONTENT)
