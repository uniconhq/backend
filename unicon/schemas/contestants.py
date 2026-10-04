"""What the registration routes take and answer with: a person's own
registration, the organisers' view of every registration in a contest, and
the bodies of registering, rejecting and giving someone more time.
"""

from datetime import datetime, timedelta
from typing import Annotated

from forge.api.contestants import Status
from pydantic import BaseModel, Field, PlainSerializer

from unicon.schemas.account import Account

SECONDS_BOUND = 10**9
"""Far past the year forge allows either way, and far inside what a time
span holds, so forge judges the value and a huge one is not a fault."""


def _whole_seconds(span: timedelta) -> int:
    return int(span.total_seconds())


Seconds = Annotated[timedelta, PlainSerializer(_whole_seconds, return_type=int)]
"""A span of time, sent as a whole number of seconds."""


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
    """The caller's own registration: where it stands, when it was made and
    last decided, why it was rejected, and how long past the contest's end
    they may still submit, in seconds.
    """

    status: Status
    registered_at: datetime
    decided_at: datetime | None
    reason: str | None
    time_extension: Seconds


class Contestant(MyRegistration):
    """One registration as the contest's organisers read it: the same
    fields, and who the person is, null once their account is gone.
    """

    user_id: int
    user: Account | None
