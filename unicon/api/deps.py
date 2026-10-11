"""What a route asks for: the session the request carries. Every route reads
what else it needs from the request and calls one forge action, which opens,
commits and closes its own transaction before the route builds a response.
"""

from typing import Annotated

from fastapi import Depends, Request
from forge.api import identity
from forge.api.errors import SessionExpired, Unauthenticated
from forge.api.types import Session

from unicon.api import cookies


async def current_session(request: Request) -> Session:
    """The session behind the cookie, checked for its lifetimes. A missing or
    altered cookie is `Unauthenticated`.
    """
    session_id = cookies.read_session_id(request)
    if session_id is None:
        raise Unauthenticated("You are not signed in. Sign in to continue.")
    return await identity.current(session_id)


CurrentSession = Annotated[Session, Depends(current_session)]


async def optional_session(request: Request) -> Session | None:
    """The session behind the cookie, or none for a request that carries no
    cookie, an altered one, or one whose session has ended: such a request
    reads as a visitor's, so a route open to visitors answers it as one.
    """
    session_id = cookies.read_session_id(request)
    if session_id is None:
        return None
    try:
        return await identity.current(session_id)
    except Unauthenticated, SessionExpired:
        return None


OptionalSession = Annotated[Session | None, Depends(optional_session)]
