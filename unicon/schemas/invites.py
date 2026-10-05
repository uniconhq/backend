"""What the invite routes take and answer with: an invite as organisers and
the person it is for see it, and the bodies of making one and of opening one
by the token its mail carried.
"""

import uuid
from datetime import datetime

from forge.api.names import ScopeNames
from forge.api.types import Grant, InviteStatus, MailStatus
from pydantic import BaseModel, Field

from unicon.schemas.account import Person

LONGEST_DAYS = 90


class InviteRequest(BaseModel):
    """Who to invite, by exactly one of `username` and `email`, to what, and
    for how many days the invite stands, 14 unless given.
    """

    grants: Grant
    username: str | None = None
    email: str | None = None
    days: int | None = Field(default=None, ge=1, le=LONGEST_DAYS)


class OpenInviteRequest(BaseModel):
    """The token after the `#` of the link an invite's mail carried."""

    token: str = Field(min_length=1, max_length=200)


class Invite(BaseModel):
    """An invite: where it is to, by its names, what it grants, the username
    or the address it names, who sent it, where it stands, whether it has
    lapsed, its dates, and what became of its mail: `waiting`, `sent`,
    `failed`, or `off` where the deployment sends no mail.
    """

    id: uuid.UUID
    where: ScopeNames
    grants: Grant
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
