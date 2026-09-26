"""What a route asks for: the settings, the runtime, a database session and
the session the request carries.
"""

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request
from forge.domain.errors import Unauthenticated
from forge.domain.sessions import Session
from forge.port import Forge
from forge.runtime import Runtime
from forge.services import identity
from forge.settings import Settings
from sqlalchemy.ext.asyncio import AsyncSession

from unicon.api import cookies


def settings_of(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def runtime_of(request: Request) -> Runtime:
    runtime: Runtime = request.app.state.runtime
    return runtime


def forge_of(request: Request) -> Forge:
    return runtime_of(request).forge


async def db_of(request: Request) -> AsyncIterator[AsyncSession]:
    async with runtime_of(request).sessions() as db:
        yield db


Config = Annotated[Settings, Depends(settings_of)]
RuntimeDep = Annotated[Runtime, Depends(runtime_of)]
ForgeDep = Annotated[Forge, Depends(forge_of)]
Db = Annotated[AsyncSession, Depends(db_of)]


async def current_session(request: Request, settings: Config, db: Db) -> Session:
    """The session behind the cookie, checked for its lifetimes. A missing or
    altered cookie is `Unauthenticated`.
    """
    session_id = cookies.read_session_id(request, settings)
    if session_id is None:
        raise Unauthenticated("No session.")
    return await identity.current(db, settings, session_id)


CurrentSession = Annotated[Session, Depends(current_session)]
