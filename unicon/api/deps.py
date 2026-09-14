"""What a handler asks for: the configuration, a database session, the Forgejo
clients and who is making the request. The clients are read off `app.state`,
which is the seam tests replace.
"""

from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from unicon.api.cookies import SESSION_COOKIE
from unicon.db.session import db_session
from unicon.domain.errors import Unauthenticated
from unicon.domain.identity import ActiveSession
from unicon.forge.protocol import Admin, Oidc
from unicon.services import sessions
from unicon.settings import Settings


def settings_of(request: Request) -> Settings:
    config: Settings = request.app.state.settings
    return config


def oidc_of(request: Request) -> Oidc:
    client: Oidc = request.app.state.oidc
    return client


def admin_of(request: Request) -> Admin:
    client: Admin = request.app.state.admin
    return client


Config = Annotated[Settings, Depends(settings_of)]
Db = Annotated[AsyncSession, Depends(db_session)]
OidcClientDep = Annotated[Oidc, Depends(oidc_of)]
AdminClientDep = Annotated[Admin, Depends(admin_of)]


async def current_session(request: Request, db: Db, settings: Config) -> ActiveSession:
    """The session the cookie names, or 401. A session that has ended also clears
    the cookie.
    """
    cookie = request.cookies.get(SESSION_COOKIE)
    if not cookie:
        raise Unauthenticated("Sign in first.")
    return await sessions.authenticate(db, settings, cookie)


CurrentSession = Annotated[ActiveSession, Depends(current_session)]
