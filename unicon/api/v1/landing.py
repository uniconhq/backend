"""The routes a visitor with no session calls, under `/public`: the contests
whose `visibility` is `public`, one of them with its released tasks, and a
released task's statement. They read no cookie and answer only what is
public; any other contest or task answers as not found, the same as one that
is not there. The contest and task are read from the path the way every
route under a scope reads them.
"""

from fastapi import APIRouter
from forge.api import contests, landing, tasks

from unicon.api.guard import ContestAtPath, TaskAtPath
from unicon.schemas.landing import PublicContest, PublicStatement

router = APIRouter(prefix="/public", tags=["public"])


@router.get("/contests", operation_id="listPublicContests", summary="The public contests")
async def list_public_contests() -> list[PublicContest]:
    """Newest start first, each without its tasks."""
    return [PublicContest.of(found) for found in await landing.contests()]


@router.get(
    "/contests/{org}/{contest}",
    operation_id="getPublicContest",
    summary="A public contest and its released tasks",
)
async def get_public_contest(scope: ContestAtPath) -> PublicContest:
    return PublicContest.of(await landing.contest(contests.contest_id_of(scope)))


@router.get(
    "/contests/{org}/{contest}/tasks/{task}",
    operation_id="getPublicStatement",
    summary="A released task's statement",
)
async def get_public_statement(scope: TaskAtPath) -> PublicStatement:
    return PublicStatement.of(await landing.statement(tasks.task_id_of(scope)))
