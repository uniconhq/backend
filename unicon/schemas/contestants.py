"""What the registration routes take and answer with: a person's own
registration, the organiser's view of every registration in a contest, and
the bodies of registering, rejecting and giving someone more time.
"""

from datetime import datetime
from typing import Literal

from forge.api.contestants import Registration as RegistrationRecord
from pydantic import BaseModel, Field

SECONDS_BOUND = 10**9
"""Far past the year forge allows either way, and far inside what a time
span holds, so forge judges the value and a huge one is not a fault."""

Status = Literal["pending", "approved", "rejected", "withdrawn", "removed"]
WorkspaceState = Literal["preparing", "ready"]


class RegisterRequest(BaseModel):
    """The code the contest asks for, when it asks for one."""

    invite_code: str | None = None


class RejectRequest(BaseModel):
    """Why, in words the person reads on their own page."""

    reason: str


class ExtensionRequest(BaseModel):
    """How long past the contest's end this person may still submit, in
    seconds, in place of any extension they had.
    """

    seconds: int = Field(ge=-SECONDS_BOUND, le=SECONDS_BOUND)


class MyRegistration(BaseModel):
    """The caller's own registration. `reason` is why it was rejected;
    `workspace` is where an approved contestant's workspace stands, `preparing`
    until every part of it is made, and null for anyone not approved.
    """

    status: Status
    reason: str | None
    registered_at: datetime
    decided_at: datetime | None
    time_extension_seconds: int
    workspace: WorkspaceState | None

    @classmethod
    def of(cls, registration: RegistrationRecord) -> MyRegistration:
        return cls(
            status=registration.status.value,
            reason=registration.reason,
            registered_at=registration.registered_at,
            decided_at=registration.decided_at,
            time_extension_seconds=int(registration.time_extension.total_seconds()),
            workspace=_workspace(registration),
        )


class Contestant(MyRegistration):
    """One registration as organisers see it: the person's own fields, who
    they are, and `workspace_error`, why the last try at a part of their
    workspace failed, while it is still being made. `username`, `name` and
    `email` are null once the person's account is gone.
    """

    user_id: int
    username: str | None
    name: str | None
    email: str | None
    avatar_url: str | None
    workspace_error: str | None

    @classmethod
    def of(cls, registration: RegistrationRecord) -> Contestant:
        user = registration.user
        return cls(
            **MyRegistration.of(registration).model_dump(),
            user_id=registration.user_id,
            username=user.username if user is not None else None,
            name=user.name if user is not None else None,
            email=user.email if user is not None else None,
            avatar_url=user.avatar_url if user is not None else None,
            workspace_error=registration.workspace_error,
        )


def _workspace(registration: RegistrationRecord) -> WorkspaceState | None:
    return registration.workspace.value if registration.workspace is not None else None
