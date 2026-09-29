"""Who holds a role at an org, a contest or a task, and adding, moving and
removing them. The same three routes are served under each kind of scope,
made by `router_at`, so each kind gets its own operation names in the
document. Listing needs the observer role at the scope and changing needs
manager; forge refuses a manager granting or removing admin, removing the
last admin, and giving a role to a contestant of the contest, and each
refusal comes back with its code.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from forge.api import roles
from forge.api.access import Organiser
from forge.api.types import Role, ScopeKind

from unicon.api.guard import PREFIX, require
from unicon.schemas.roles import GrantRequest, Holder

NO_CONTENT = status.HTTP_204_NO_CONTENT


def router_at(kind: ScopeKind) -> APIRouter:
    """The role routes under the prefix of `kind`."""
    name = kind.value.capitalize()
    router = APIRouter(prefix=PREFIX[kind], tags=["roles"])
    Observer = Annotated[Organiser, Depends(require(Role.OBSERVER, kind))]
    Manager = Annotated[Organiser, Depends(require(Role.MANAGER, kind))]

    @router.get(
        "/roles",
        operation_id=f"list{name}Roles",
        summary=f"Who holds a role at the {kind.value}",
    )
    async def list_roles(organiser: Observer) -> list[Holder]:
        """Everyone holding a role here, each once with the highest role they
        hold, highest first, including those who hold it at a broader scope.
        """
        return [
            Holder.of(holder, organiser.scope)
            for holder in await roles.holders(organiser, organiser.scope)
        ]

    @router.post(
        "/roles",
        operation_id=f"grant{name}Role",
        summary=f"Give someone a role at the {kind.value}",
        status_code=NO_CONTENT,
    )
    async def grant_role(organiser: Manager, body: GrantRequest) -> Response:
        """A different role than the one they hold here moves them to it,
        which is how a person is promoted or demoted.
        """
        await roles.grant(organiser, organiser.scope, body.username, Role(body.role))
        return Response(status_code=NO_CONTENT)

    @router.delete(
        "/roles/{user_id}",
        operation_id=f"revoke{name}Role",
        summary=f"Take away someone's role at the {kind.value}",
        status_code=NO_CONTENT,
    )
    async def revoke_role(organiser: Manager, user_id: int) -> Response:
        """Every role they hold directly here goes; a role they hold at a
        broader scope stays.
        """
        await roles.revoke(organiser, organiser.scope, user_id)
        return Response(status_code=NO_CONTENT)

    return router
