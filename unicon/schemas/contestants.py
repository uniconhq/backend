"""What the registration routes take and answer with: a person's own
registration, the organisers' view of every registration in a contest, and
the bodies of registering, rejecting and giving someone or a team more
time.
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

TASKS_BOUND = 1000
"""Far more tasks than a contest lists, so forge judges the names and a long
list is refused before it is read."""


class RegisterRequest(BaseModel):
    """The code the contest asks for, when it asks for one."""

    invite_code: str | None = None


class RejectRequest(BaseModel):
    """Why, in words the person reads on their own page."""

    reason: str


class ExtensionRequest(BaseModel):
    """How long, in seconds, the extension moves the due and the close of
    each of the contest's `tasks`, by name, or of every task when it names
    none, in place of any extension there was.
    """

    seconds: int = Field(ge=-SECONDS_BOUND, le=SECONDS_BOUND)
    tasks: list[str] | None = Field(default=None, max_length=TASKS_BOUND)


class MyRegistration(BaseModel):
    """The caller's own registration: where it stands, when it was made and
    last decided, why it was rejected, and their own extension: how long, in
    seconds, it moves the due and the close of the tasks in
    `extension_tasks`, or of every task when that is null. It holds while
    they work alone; in a team, the team's holds.
    """

    status: Status
    registered_at: datetime
    decided_at: datetime | None
    reason: str | None
    time_extension: Seconds
    extension_tasks: list[str] | None


class Contestant(MyRegistration):
    """One registration as the contest's organisers read it: the same
    fields, and who the person is, null once their account is gone.
    """

    user_id: int
    user: Account | None
