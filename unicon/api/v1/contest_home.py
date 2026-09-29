"""What a signed-in person reads of the contests they may see: the list of
them, a contest's home and a task's page. Each needs a session and no role;
forge applies the contest's visibility and the release rules, and a contest
or task the caller may not see answers as not found, the same as one that is
not there.
"""

from fastapi import APIRouter
from forge.api import contest_home, contests, tasks
from forge.api.types import ScopeKind

from unicon.api.deps import CurrentSession
from unicon.api.guard import PREFIX, ContestAtPath, TaskAtPath
from unicon.schemas.contest_home import ContestHome, ContestSummary, TaskPage

CONTEST = PREFIX[ScopeKind.CONTEST]
TASK = PREFIX[ScopeKind.TASK]

router = APIRouter(tags=["contest home"])


@router.get(
    "/contests",
    operation_id="listMyContests",
    summary="Every published contest the caller may enter or has entered",
)
async def list_my_contests(session: CurrentSession) -> list[ContestSummary]:
    """Newest start first, each with the caller's own status. An organiser
    finds their own contests from their orgs.
    """
    return [ContestSummary.of(found) for found in await contest_home.contests(session)]


@router.get(f"{CONTEST}/home", operation_id="getContestHome", summary="The contest's home")
async def get_contest_home(session: CurrentSession, scope: ContestAtPath) -> ContestHome:
    """The contest's dates, the caller's registration and own deadline, the
    server's clock, and the tasks released to the caller.
    """
    return ContestHome.of(await contest_home.home(session, contests.contest_id_of(scope)))


@router.get(f"{TASK}/page", operation_id="getTaskPage", summary="A released task's page")
async def get_task_page(session: CurrentSession, scope: TaskAtPath) -> TaskPage:
    """The statement and the limits a submit is checked against."""
    return TaskPage.of(await contest_home.task(session, tasks.task_id_of(scope)))
