"""What the invite routes take and answer with: an invite as organisers and
the person it is for see it, what accepting one did, and the bodies of
making one, of opening one by the token its mail carried and of accepting
one with a code.
"""

import uuid
from datetime import datetime
from typing import Literal

from forge.api.names import ScopeNames
from forge.api.types import Grant, InviteStatus, MailStatus
from pydantic import BaseModel, Field

from unicon.schemas.account import Person
from unicon.schemas.entrants import Entered, EntrantRef

LONGEST_DAYS = 90


class InviteRequest(BaseModel):
    """Who to invite, by exactly one of `username` and `email`, to what, for
    how many days the invite stands, 14 unless given, and, for a place in a
    contest, the `entrant` it puts them straight into, by its id, or none to
    register them on their own. A member's place in an entrant is offered by
    the entrant's members, never here.
    """

    grants: Literal["admin", "manager", "observer", "contestant"]
    username: str | None = None
    email: str | None = None
    days: int | None = Field(default=None, ge=1, le=LONGEST_DAYS)
    entrant: uuid.UUID | None = None


class AcceptRequest(BaseModel):
    """The code a sign-up asks for, when joining an entrant by a member's
    invite needs one.
    """

    code: str | None = Field(default=None, max_length=400)


class OpenInviteRequest(BaseModel):
    """The token after the `#` of the link an invite's mail carried."""

    token: str = Field(min_length=1, max_length=200)


class Invite(BaseModel):
    """An invite: where it is to, by its names, and the title of the contest
    it is at or under, null at an org; what it grants, a place in a
    contest (`contestant`), a member's place in an entrant (`member`) or an
    organiser role, the entrant it asks someone into, if any, the username
    or the address it names, who sent it, where it stands, whether it has
    lapsed, its dates, and what became of its mail: `waiting`, `sent`,
    `failed`, or `off` where the deployment sends no mail.
    """

    id: uuid.UUID
    where: ScopeNames
    contest_title: str | None
    grants: Grant
    entrant: EntrantRef | None
    username: str | None
    email: str | None
    invited_by: Person | None
    status: InviteStatus
    expired: bool
    created_at: datetime
    expires_at: datetime
    decided_at: datetime | None
    mail_status: MailStatus
    mailed_at: datetime | None


class AcceptedInvite(BaseModel):
    """What accepting an invite did: the invite as it stands now, and, for a
    place in a contest, the entrant the caller is in now, null for a role.
    """

    invite: Invite
    entered: Entered | None
