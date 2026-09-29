"""The one check in front of every organiser route. `require(role, at)` is a
dependency that reads the session, builds the scope from the route's path,
asks forge once whether the caller holds at least `role` there, counting
roles held at broader scopes, and hands the route the `Organiser` forge
returns. The action the route then calls takes that `Organiser` and reads
no roles of its own, so a request reads them once. A caller below the role
is refused with `forbidden` before the route runs.

The URL of each kind of scope is here too, beside the function that reads a
scope back out of it, so the path and the scope it names are written in one
place: `/orgs/{org}`, `/orgs/{org}/contests/{contest}` and
`/orgs/{org}/contests/{contest}/tasks/{task}`. `TaskAtPath` is the task
scope read that way, for the one route under a task that needs a session and
no role.
"""

from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import Depends
from forge.api import access
from forge.api.access import Organiser
from forge.api.types import Role, Scope, ScopeKind

from unicon.api.deps import CurrentSession

PREFIX = {
    ScopeKind.ORG: "/orgs/{org}",
    ScopeKind.CONTEST: "/orgs/{org}/contests/{contest}",
    ScopeKind.TASK: "/orgs/{org}/contests/{contest}/tasks/{task}",
}


async def _org(org: str) -> Scope:
    return Scope(org)


async def _contest(org: str, contest: str) -> Scope:
    return Scope(org, contest)


async def _task(org: str, contest: str, task: str) -> Scope:
    return Scope(org, contest, task)


SCOPE_FROM_PATH: dict[ScopeKind, Callable[..., Awaitable[Scope]]] = {
    ScopeKind.ORG: _org,
    ScopeKind.CONTEST: _contest,
    ScopeKind.TASK: _task,
}

TaskAtPath = Annotated[Scope, Depends(_task)]


def require(role: Role, at: ScopeKind = ScopeKind.ORG) -> Callable[..., Awaitable[Organiser]]:
    """The dependency for a route under the `at` prefix that needs `role`
    there. Its path parameters are the ones that prefix names.
    """
    scope_from_path = SCOPE_FROM_PATH[at]

    async def guard(
        session: CurrentSession, scope: Annotated[Scope, Depends(scope_from_path)]
    ) -> Organiser:
        return await access.organiser(session, scope, role)

    return guard
