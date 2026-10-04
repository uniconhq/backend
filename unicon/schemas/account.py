"""What the account routes answer with, and a person as the other answers
name them.
"""

import uuid
from datetime import datetime

from forge.api.names import ScopeNames
from forge.api.types import Role
from pydantic import BaseModel


class Person(BaseModel):
    """Someone as another person sees them, by their forge id. Their email
    stays out.
    """

    id: int
    username: str
    name: str | None
    avatar_url: str | None


class Account(Person):
    """Someone with their email, as they see themself and as the organisers
    of a contest they registered for see them.
    """

    email: str | None


class HeldRole(BaseModel):
    """A role the user holds, at the org, contest or task `names` reaches."""

    role: Role
    names: ScopeNames


class Me(BaseModel):
    """The signed-in user and their roles at every scope. `degraded` is set
    when the forge did not answer and the identity comes from the session.
    """

    user: Account
    roles: list[HeldRole]
    degraded: bool


class SessionInfo(BaseModel):
    """One place this user is signed in, described by its device and its
    times. The address a session came from is kept for the record and stays
    out of the answer.
    """

    id: uuid.UUID
    created_at: datetime
    last_seen_at: datetime
    user_agent: str | None
    current: bool
