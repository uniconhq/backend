"""The one check in front of every organiser route. `require(role, at)` is a
dependency that reads the session, builds the scope from the route's path,
asks forge once whether the caller holds at least `role` there, counting
roles held at broader scopes, and hands the route the `Organiser` forge
returns. The action the route then calls takes that `Organiser` and reads
no roles of its own, so a request reads them once. A caller below the role
is refused with `forbidden` before the route runs.

A few reads are open to anyone holding any role at the scope or at anything
in it, and the action narrows what each reads to where they hold one:
`anywhere(at)` is their dependency. It asks as `require(Role.OBSERVER, at)`
does first, so an observer there costs the same one read; someone holding
roles only further in has their roles read once more to find one, and the
`Organiser` is theirs at that narrower scope. Holding none, or naming a
scope that is not there, is `forbidden`, naming the address.

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
from forge.api import access, identity, names
from forge.api.access import Organiser
from forge.api.errors import Forbidden, NotFound
from forge.api.types import Role, Scope, ScopeKind, Session

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


def anywhere(at: ScopeKind = ScopeKind.ORG) -> Guard:
    """The dependency for a route under the `at` prefix, an org or a
    contest, open to anyone holding a role there or at anything in it.
    """
    return ANYWHERE[at]


async def _held_under(session: Session, org: str, contest: str | None = None) -> Organiser:
    """The caller as an observer of the scope the names name, or, holding no
    role there, as an organiser at a scope in it where they hold one.
    """
    try:
        return await access.organiser_at(session, Role.OBSERVER, org, contest)
    except Forbidden:
        address = "/".join(part for part in (org, contest) if part is not None)
        refused = Forbidden(f"This needs a role at {address} or at anything in it.")
    try:
        scope = await names.scope_at(org, contest)
    except NotFound:
        raise refused from None
    held = await identity.whoami(session)
    under = next((role.scope for role in held.roles if scope.covers(role.scope)), None)
    if under is None:
        raise refused
    return await access.organiser(session, under, Role.OBSERVER)


def _anywhere_in_org() -> Guard:
    async def guard(session: CurrentSession, org: str) -> Organiser:
        return await _held_under(session, org)

    return guard


def _anywhere_in_contest() -> Guard:
    async def guard(session: CurrentSession, org: str, contest: str) -> Organiser:
        return await _held_under(session, org, contest)

    return guard


ANYWHERE: dict[ScopeKind, Guard] = {
    ScopeKind.ORG: _anywhere_in_org(),
    ScopeKind.CONTEST: _anywhere_in_contest(),
}
