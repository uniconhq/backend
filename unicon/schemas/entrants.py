"""What the entrant routes take and answer with: an entrant as its members
and as the contest's organisers read it, the caller's registration panel,
what accepting a place in a contest did, and the bodies of registering,
inviting, renaming, rejecting, moving someone and giving an entrant more
time.
"""

import uuid
from datetime import datetime, timedelta
from typing import Annotated

from forge.api.entrants import Locks, Status, WayKind
from pydantic import BaseModel, Field, PlainSerializer

from unicon.schemas.account import Account, Person

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
NAME_BOUND = 120
"""Twice forge's limit on an entrant's name, which forge checks after
trimming, so a long one is refused before it is read."""
TEXT_BOUND = 400
"""Far more than a username, an address or a code holds; forge judges each."""


class RegisterRequest(BaseModel):
    """The new entrant's name, needed when the contest's entrants may be more
    than one person and refused when they are one each, and the code a
    sign-up asks for, when the caller is asked for one.
    """

    name: str | None = Field(default=None, max_length=NAME_BOUND)
    code: str | None = Field(default=None, max_length=TEXT_BOUND)


class MemberInviteRequest(BaseModel):
    """Who to ask into the caller's entrant, by exactly one of `username` and
    `email`.
    """

    username: str | None = Field(default=None, max_length=TEXT_BOUND)
    email: str | None = Field(default=None, max_length=TEXT_BOUND)


class NameRequest(BaseModel):
    """An entrant's new name."""

    name: str = Field(max_length=NAME_BOUND)


class RejectRequest(BaseModel):
    """Why, in words the entrant's members read on their own page."""

    reason: str


class ExtensionRequest(BaseModel):
    """How long, in seconds, the extension moves the due and the close of
    each of the contest's `tasks`, by name, or of every task when it names
    none, in place of any extension there was.
    """

    seconds: int = Field(ge=-SECONDS_BOUND, le=SECONDS_BOUND)
    tasks: list[str] | None = Field(default=None, max_length=TASKS_BOUND)


class MoveRequest(BaseModel):
    """The entrant of the same contest to move the member to, by its id."""

    to: uuid.UUID


class Member(BaseModel):
    """Someone in an entrant: their id, who they are, null once their account
    is gone, the way they came in by, `invite`, `signup` or `organiser`, that
    way's name, if it has one, and when they joined.
    """

    user_id: int
    user: Person | None
    way_kind: WayKind
    way_name: str | None
    joined_at: datetime


class OrganisedMember(Member):
    """A member as the contest's organisers read them, with their email."""

    user: Account | None


class InvitedIn(BaseModel):
    """An invite into an entrant still waiting: its id, the username or the
    address it names, who sent it, whether an organiser sent it, and when it
    lapses.
    """

    invite: uuid.UUID
    username: str | None
    email: str | None
    invited_by: int
    by_organiser: bool
    expires_at: datetime


class EntrantFields(BaseModel):
    """What every reader of an entrant reads: its id, its own name, null for
    an entrant of one in a contest whose entrants are one person each, and
    the name it is shown under, its member's username then; where its
    registration stands, when it was made and the last decision on it, with
    why for a rejection; the invites into it still waiting; its extension,
    how long, in seconds, it moves the due and the close of the tasks in
    `extension_tasks`, or of every task when that is null; whether it has
    submitted, whether it has as many members as the contest asks, and
    whether its roster has locked.
    """

    id: uuid.UUID
    name: str | None
    display_name: str
    status: Status
    registered_at: datetime
    decided_at: datetime | None
    reason: str | None
    invites: list[InvitedIn]
    time_extension: Seconds
    extension_tasks: list[str] | None
    submitted: bool
    complete: bool
    locked: bool


class Entrant(EntrantFields):
    """An entrant as its members read it, with its members."""

    members: list[Member]


class OrganisedEntrant(EntrantFields):
    """An entrant as the contest's organisers read it, its members with
    their email.
    """

    members: list[OrganisedMember]


class EntrantRef(BaseModel):
    """An entrant by its id and the name it is shown under."""

    id: uuid.UUID
    name: str


class Invitation(BaseModel):
    """One of the caller's own invites into an entrant of the contest, still
    waiting: the invite, the entrant, whether an organiser sent it, and when
    it lapses.
    """

    invite: uuid.UUID
    entrant: EntrantRef
    by_organiser: bool
    expires_at: datetime


class Refusal(BaseModel):
    """Why the caller cannot register now: the code registering would be
    refused with, and its sentence.
    """

    code: str
    detail: str


class MyEntry(BaseModel):
    """The caller's registration panel: their entrant, if any, their own
    invites into the contest's entrants, whether the registration window is
    open, whether they can register and, when they cannot, why; whether to
    ask them for a code, true only when a code would let them in; and the
    contest's sizes, the most and the fewest people in an entrant, and when
    an entrant's roster locks, at the `start` or at its `first_submission`.
    """

    entrant: Entrant | None
    invitations: list[Invitation]
    registration_open: bool
    can_register: bool
    asks_code: bool
    refused: Refusal | None
    most: int
    fewest: int
    locks: Locks


class Entered(BaseModel):
    """What accepting a place in a contest did: the entrant the caller is in
    now, its status, and whether accepting `made` it, `joined` it, or found
    them in it `already`.
    """

    entrant: EntrantRef
    status: Status
    how: str
