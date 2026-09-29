"""What the role routes take and answer with."""

from typing import Literal

from forge.api.roles import Holder as HolderRecord
from forge.api.types import Scope as ScopeValue
from pydantic import BaseModel

from unicon.schemas.scope import Scope

RoleName = Literal["admin", "manager", "observer"]


class Holder(BaseModel):
    """Someone holding `role` at the scope asked about. `scope` is where
    they hold it directly, and `inherited` is set when that is a broader
    scope, such as an org admin listed at one of the org's contests.
    """

    user_id: int
    username: str
    name: str | None
    avatar_url: str | None
    role: RoleName
    scope: Scope
    inherited: bool

    @classmethod
    def of(cls, holder: HolderRecord, asked: ScopeValue) -> Holder:
        return cls(
            user_id=holder.user.id,
            username=holder.user.username,
            name=holder.user.name,
            avatar_url=holder.user.avatar_url,
            role=holder.role.value,
            scope=Scope.of(holder.at),
            inherited=holder.at != asked,
        )


class GrantRequest(BaseModel):
    """Give the named user `role` at the scope, moving them from any other
    role they hold directly there.
    """

    username: str
    role: RoleName
