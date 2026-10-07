"""Teams in a contest whose settings turn them on. A contestant reads their
own place among the contest's teams, lists the teams, makes one, asks to
join one, takes the request back and leaves, with a session alone, since
forge checks they are the contest's approved contestant. The leader asks
someone in, lets a request in and removes a member, and forge checks the
caller leads the team named. Organisers list every team with the observer
role at the contest, and make, delete and mend them, and give one more
time, with manager. Every refusal comes back with forge's code, such as
`team_full`, `in_team` or `submitted_alone`.
"""

import uuid
from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from forge.api import contests, teams
from forge.api.access import Organiser
from forge.api.types import Role, ScopeKind

from unicon.api.deps import CurrentSession
from unicon.api.guard import PREFIX, ContestAtPath, require
from unicon.schemas.contestants import ExtensionRequest
from unicon.schemas.teams import (
    InviteToTeamRequest,
    ListedTeam,
    MyTeams,
    OrganiseTeamRequest,
    PersonRequest,
    Team,
    TeamRequest,
)

CREATED = status.HTTP_201_CREATED
NO_CONTENT = status.HTTP_204_NO_CONTENT
CONTEST = PREFIX[ScopeKind.CONTEST]
TEAM = f"{CONTEST}/teams/{{team_id}}"
ORGANISE = f"{CONTEST}/organise/teams"

router = APIRouter(tags=["teams"])

ContestObserver = Annotated[Organiser, Depends(require(Role.OBSERVER, ScopeKind.CONTEST))]
ContestManager = Annotated[Organiser, Depends(require(Role.MANAGER, ScopeKind.CONTEST))]


@router.get(
    f"{CONTEST}/my-team",
    operation_id="getMyTeam",
    summary="The caller's team in the contest, and the teams they asked or are asked into",
    response_model=MyTeams,
)
async def get_my_team(session: CurrentSession, scope: ContestAtPath) -> teams.Mine:
    return await teams.mine(session, contests.contest_id_of(scope))


@router.get(
    f"{CONTEST}/teams",
    operation_id="listTeams",
    summary="The contest's teams, for an approved contestant choosing one",
    response_model=list[ListedTeam],
)
async def list_teams(session: CurrentSession, scope: ContestAtPath) -> tuple[teams.Listed, ...]:
    return await teams.listed(session, contests.contest_id_of(scope))


@router.post(
    f"{CONTEST}/teams",
    operation_id="createTeam",
    summary="Make a team, led by the caller",
    status_code=CREATED,
    response_model=Team,
)
async def create_team(
    session: CurrentSession, scope: ContestAtPath, body: TeamRequest
) -> teams.Team:
    return await teams.create(session, contests.contest_id_of(scope), body.name)


@router.post(
    f"{TEAM}/request",
    operation_id="requestToJoinTeam",
    summary="Ask to join a team, or accept its invitation",
    response_model=Team,
)
async def request_to_join(
    session: CurrentSession, scope: ContestAtPath, team_id: uuid.UUID
) -> teams.Team:
    return await teams.request(session, contests.contest_id_of(scope), team_id)


@router.post(
    f"{TEAM}/cancel",
    operation_id="cancelTeamRequest",
    summary="Take back a request to join a team, or decline its invitation",
    status_code=NO_CONTENT,
)
async def cancel_request(
    session: CurrentSession, scope: ContestAtPath, team_id: uuid.UUID
) -> Response:
    await teams.cancel(session, contests.contest_id_of(scope), team_id)
    return Response(status_code=NO_CONTENT)


@router.post(
    f"{CONTEST}/my-team/leave",
    operation_id="leaveTeam",
    summary="Leave the caller's team",
    status_code=NO_CONTENT,
)
async def leave_team(session: CurrentSession, scope: ContestAtPath) -> Response:
    """Access to the team's workspace goes; what the team made stays its own."""
    await teams.leave(session, contests.contest_id_of(scope))
    return Response(status_code=NO_CONTENT)


@router.post(
    f"{TEAM}/invite",
    operation_id="inviteToTeam",
    summary="Ask an approved contestant into the caller's team, as its leader",
    response_model=Team,
)
async def invite_to_team(
    session: CurrentSession, scope: ContestAtPath, team_id: uuid.UUID, body: InviteToTeamRequest
) -> teams.Team:
    return await teams.invite(session, contests.contest_id_of(scope), team_id, body.username)


@router.post(
    f"{TEAM}/members/{{user_id}}/approve",
    operation_id="approveTeamMember",
    summary="Let in someone who asked to join, as the team's leader",
    response_model=Team,
)
async def approve_member(
    session: CurrentSession, scope: ContestAtPath, team_id: uuid.UUID, user_id: int
) -> teams.Team:
    return await teams.approve(session, contests.contest_id_of(scope), team_id, user_id)


@router.delete(
    f"{TEAM}/members/{{user_id}}",
    operation_id="removeTeamMember",
    summary="Take someone out of the team, or turn down their request, as its leader",
    response_model=Team,
)
async def remove_member(
    session: CurrentSession, scope: ContestAtPath, team_id: uuid.UUID, user_id: int
) -> teams.Team:
    return await teams.remove(session, contests.contest_id_of(scope), team_id, user_id)


@router.get(
    ORGANISE,
    operation_id="listEveryTeam",
    summary="Every team of the contest with its members",
    response_model=list[Team],
)
async def list_every_team(organiser: ContestObserver) -> tuple[teams.Team, ...]:
    return await teams.every(organiser, contests.contest_id_of(organiser.scope))


@router.post(
    ORGANISE,
    operation_id="organiseCreateTeam",
    summary="Make a team, empty or led by a named approved contestant",
    status_code=CREATED,
    response_model=Team,
)
async def organise_create(organiser: ContestManager, body: OrganiseTeamRequest) -> teams.Team:
    return await teams.organise_create(
        organiser, contests.contest_id_of(organiser.scope), body.name, leader=body.leader
    )


@router.delete(
    f"{ORGANISE}/{{team_id}}",
    operation_id="organiseDeleteTeam",
    summary="Delete a team that has submitted nothing",
    status_code=NO_CONTENT,
)
async def organise_delete(organiser: ContestManager, team_id: uuid.UUID) -> Response:
    await teams.organise_delete(organiser, contests.contest_id_of(organiser.scope), team_id)
    return Response(status_code=NO_CONTENT)


@router.post(
    f"{ORGANISE}/{{team_id}}/members",
    operation_id="organiseMoveIntoTeam",
    summary="Put an approved contestant in the team, out of any other",
    response_model=Team,
)
async def organise_move(
    organiser: ContestManager, team_id: uuid.UUID, body: PersonRequest
) -> teams.Team:
    return await teams.organise_move(
        organiser, contests.contest_id_of(organiser.scope), body.user_id, team_id
    )


@router.delete(
    f"{ORGANISE}/{{team_id}}/members/{{user_id}}",
    operation_id="organiseRemoveFromTeam",
    summary="Take someone out of the team, or drop their request or invitation",
    response_model=Team,
)
async def organise_remove(
    organiser: ContestManager, team_id: uuid.UUID, user_id: int
) -> teams.Team:
    return await teams.organise_remove(
        organiser, contests.contest_id_of(organiser.scope), team_id, user_id
    )


@router.put(
    f"{ORGANISE}/{{team_id}}/leader",
    operation_id="organiseSetTeamLeader",
    summary="Make a member the team's leader",
    response_model=Team,
)
async def organise_lead(
    organiser: ContestManager, team_id: uuid.UUID, body: PersonRequest
) -> teams.Team:
    return await teams.organise_lead(
        organiser, contests.contest_id_of(organiser.scope), team_id, body.user_id
    )


@router.put(
    f"{ORGANISE}/{{team_id}}/extension",
    operation_id="organiseExtendTeam",
    summary="Give a team more time on the contest's tasks",
    response_model=Team,
)
async def organise_extend(
    organiser: ContestManager, team_id: uuid.UUID, body: ExtensionRequest
) -> teams.Team:
    """It moves the team's due and close on the named tasks, or on every
    task when none are named, in place of any extension it had; zero takes
    it away. One that names a task the contest does not list, would let the
    team submit to a task whose reveal has passed, or would leave one of its
    submissions after the due or the close it was made before is
    `invalid_extension`.
    """
    return await teams.organise_extend(
        organiser,
        contests.contest_id_of(organiser.scope),
        team_id,
        timedelta(seconds=body.seconds),
        tasks=body.tasks,
    )
