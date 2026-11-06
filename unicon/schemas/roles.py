"""What the role routes take and answer with."""

from forge.api.names import ScopeNames
from forge.api.types import Role
from pydantic import BaseModel

from unicon.schemas.account import Person


class Holder(BaseModel):
    """Someone holding `role` at the scope asked about, held directly at
    `at_names`: that scope, or a broader one, such as the org of a contest
    whose admin is listed at the contest. `may_change` says whether the
    caller may change or take the role, held here and not above.
    """

    user: Person
    role: Role
    at_names: ScopeNames
    may_change: bool


class GrantRequest(BaseModel):
    """Give the named user `role` at the scope, moving them from any other
    role they hold directly there.
    """

    username: str
    role: Role
