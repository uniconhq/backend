"""What a route asks for: the settings, the runtime, a unit of work with its
context, and the session the request carries. The unit of work commits when
the route returns and rolls back when it raises, so a service never commits.
"""

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request
from forge.context import Context
from forge.domain.errors import Unauthenticated
from forge.domain.sessions import Session
from forge.runtime import Runtime
from forge.services import identity
from sqlalchemy.ext.asyncio import AsyncSession

from unicon.api import cookies
from unicon.settings import ShellSettings


def settings_of(request: Request) -> ShellSettings:
    settings: ShellSettings = request.app.state.settings
    return settings


def runtime_of(request: Request) -> Runtime:
    runtime: Runtime = request.app.state.runtime
    return runtime


async def unit_of_work(request: Request) -> AsyncIterator[AsyncSession]:
    async with runtime_of(request).sessions() as db:
        try:
            yield db
        except BaseException:
            await db.rollback()
            raise
        await db.commit()


Config = Annotated[ShellSettings, Depends(settings_of)]
RuntimeDep = Annotated[Runtime, Depends(runtime_of)]
Db = Annotated[AsyncSession, Depends(unit_of_work)]


def context_of(request: Request, db: Db) -> Context:
    return runtime_of(request).context(db)


Ctx = Annotated[Context, Depends(context_of)]


async def current_session(request: Request, settings: Config, ctx: Ctx) -> Session:
    """The session behind the cookie, checked for its lifetimes. A missing or
    altered cookie is `Unauthenticated`.
    """
    session_id = cookies.read_session_id(request, settings)
    if session_id is None:
        raise Unauthenticated("No session.")
    return await identity.current(ctx, session_id)


CurrentSession = Annotated[Session, Depends(current_session)]
