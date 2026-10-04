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
`/orgs/{org}/contests/{contest}/tasks/{task}`. The names in the path are
labels: forge turns them into the scope of keys a role is held at. For an
organiser route a part that is not there is `forbidden` like a scope the
caller may not reach, unless they hold the role above it, so the routes
tell nobody else what exists. `ContestAtPath` and `TaskAtPath` are the
contest and task scopes read from the path, `not_found` naming the first
part that is not there, for the routes a contestant calls, which need a
session and no role.
"""

from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import Depends
from forge.api import access, names
from forge.api.access import Organiser
from forge.api.types import Role, Scope, ScopeKind

from unicon.api.deps import CurrentSession

PREFIX = {
    ScopeKind.ORG: "/orgs/{org}",
    ScopeKind.CONTEST: "/orgs/{org}/contests/{contest}",
    ScopeKind.TASK: "/orgs/{org}/contests/{contest}/tasks/{task}",
}


async def _contest(org: str, contest: str) -> Scope:
    return await names.scope_at(org, contest)


async def _task(org: str, contest: str, task: str) -> Scope:
    return await names.scope_at(org, contest, task)


ContestAtPath = Annotated[Scope, Depends(_contest)]
TaskAtPath = Annotated[Scope, Depends(_task)]


def require(role: Role, at: ScopeKind = ScopeKind.ORG) -> Callable[..., Awaitable[Organiser]]:
    """The dependency for a route under the `at` prefix that needs `role`
    there. Its path parameters are the ones that prefix names.
    """
    return GUARDS[at](role)


Guard = Callable[..., Awaitable[Organiser]]


def _at_org(role: Role) -> Guard:
    async def guard(session: CurrentSession, org: str) -> Organiser:
        return await access.organiser_at(session, role, org)

    return guard


def _at_contest(role: Role) -> Guard:
    async def guard(session: CurrentSession, org: str, contest: str) -> Organiser:
        return await access.organiser_at(session, role, org, contest)

    return guard


def _at_task(role: Role) -> Guard:
    async def guard(session: CurrentSession, org: str, contest: str, task: str) -> Organiser:
        return await access.organiser_at(session, role, org, contest, task)

    return guard


GUARDS: dict[ScopeKind, Callable[[Role], Guard]] = {
    ScopeKind.ORG: _at_org,
    ScopeKind.CONTEST: _at_contest,
    ScopeKind.TASK: _at_task,
}
