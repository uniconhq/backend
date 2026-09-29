"""A scope as the API writes it: an org, a contest in it, or a task in that."""

from forge.api.types import Scope as ScopeValue
from pydantic import BaseModel


class Scope(BaseModel):
    kind: str
    org: str
    contest: str | None
    task: str | None

    @classmethod
    def of(cls, scope: ScopeValue) -> Scope:
        return cls(kind=scope.kind.value, org=scope.org, contest=scope.contest, task=scope.task)
