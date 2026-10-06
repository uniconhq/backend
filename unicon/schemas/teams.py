"""What the team routes take and answer with: a team with its members and the
people asking or asked in, a team as someone choosing one sees it, the
caller's own place among a contest's teams, and the bodies of the actions.
"""

import uuid
from datetime import datetime

from forge.api.types import MemberStatus
from pydantic import BaseModel, Field

from unicon.schemas.account import Person
from unicon.schemas.contestants import Seconds


class Member(BaseModel):
    """Someone in a team, or asking or asked to be: their id, who they are,
    or none once their account is gone, where they stand, and since when.
    """

    user_id: int
    user: Person | None
    status: MemberStatus
    since: datetime


class Team(BaseModel):
    """A team: its name, its leader's user id, its members, the people
    asking or asked in, whether it has submitted anything, and its
    extension: how long, in seconds, it moves the due and the close of the
    tasks in `extension_tasks`, or of every task when that is null.
    """

    id: uuid.UUID
    name: str
    leader: int | None
    members: list[Member]
    pending: list[Member]
    submitted: bool
    time_extension: Seconds
    extension_tasks: list[str] | None


class ListedTeam(BaseModel):
    """A team as a contestant choosing one sees it: its name, its leader, and
    how many are in it of how many the contest allows.
    """

    id: uuid.UUID
    name: str
    leader: Person | None
    size: int
    max_size: int


class MyTeams(BaseModel):
    """The caller's team in the contest, if any, the teams they are asked
    into or have asked to join, and how many a team holds.
    """

    team: Team | None
    invited_to: list[ListedTeam]
    requested: list[ListedTeam]
    max_size: int


NAME_MAX = 60
"""Forge's limit on a team's name, checked there too, after trimming."""


class TeamRequest(BaseModel):
    """A new team's name."""

    name: str = Field(max_length=NAME_MAX * 2)


class OrganiseTeamRequest(TeamRequest):
    """A new team's name, and the username of the approved contestant who
    leads it, or none for an empty team.
    """

    leader: str | None = None


class InviteToTeamRequest(BaseModel):
    """The username of the approved contestant the leader asks in."""

    username: str


class PersonRequest(BaseModel):
    """Who, by their user id."""

    user_id: int
