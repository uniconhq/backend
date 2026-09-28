"""What a route asks for: the session the request carries. Every route reads
what else it needs from the request and calls one forge action, which opens,
commits and closes its own transaction before the route builds a response.
"""

from typing import Annotated

from fastapi import Depends, Request
from forge.api import identity
from forge.api.errors import Unauthenticated
from forge.api.types import Session

from unicon.api import cookies


async def current_session(request: Request) -> Session:
    """The session behind the cookie, checked for its lifetimes. A missing or
    altered cookie is `Unauthenticated`.
    """
    session_id = cookies.read_session_id(request)
    if session_id is None:
        raise Unauthenticated("No session.")
    return await identity.current(session_id)


CurrentSession = Annotated[Session, Depends(current_session)]
