"""The contest's boards and the marks a row holds for a board reading them.

Until audiences come, a board is read by staff alone: someone with the
observer role at the contest reads every board, every row and cell, with
no hold. Anyone else, a visitor under `/public` included, reads none, so a
list comes back empty and one board is no such board, the same as one
that is not there.

A contestant reads, marks and unmarks their entrant's own submissions to a task
with a session alone; forge checks the submission is the row's, the task
has marks, how many the row may hold and that its close has not passed,
answering `marks_off`, `mark_limit` with `limit` and `marks_frozen`.
"""

from typing import Annotated, Any

from fastapi import APIRouter, Path
from forge.api import boards, contests, tasks
from forge.api.errors import NotFound
from forge.api.types import ScopeKind

from unicon.api.deps import CurrentSession
from unicon.api.guard import PREFIX, ContestAtPath, TaskAtPath
from unicon.api.v1.submissions import Number
from unicon.schemas.boards import Board, Marks, board_of

CONTEST = PREFIX[ScopeKind.CONTEST]
TASK = PREFIX[ScopeKind.TASK]
PUBLIC = "/public/contests/{org}/{contest}"
NO_SUCH_BOARD = "There is no such leaderboard."

router = APIRouter(tags=["boards"])

BoardKey = Annotated[str, Path(description="The board's key in `leaderboards`")]


def _listed(found: tuple[boards.Board, ...]) -> list[dict[str, Any]]:
    return [board_of(each) for each in found]


def _named(found: tuple[boards.Board, ...], board: str) -> dict[str, Any]:
    for each in found:
        if each.key == board:
            return board_of(each)
    raise NotFound(NO_SUCH_BOARD)


@router.get(
    f"{PUBLIC}/boards",
    operation_id="listPublicBoards",
    summary="The boards of a public contest that everyone sees",
    response_model=list[Board],
    tags=["public"],
)
async def list_public_boards(scope: ContestAtPath) -> list[dict[str, Any]]:
    """None until audiences come."""
    return _listed(await boards.seen(None, contests.contest_id_of(scope)))


@router.get(
    f"{PUBLIC}/boards/{{board}}",
    operation_id="getPublicBoard",
    summary="One board of a public contest that everyone sees",
    response_model=Board,
    tags=["public"],
)
async def get_public_board(scope: ContestAtPath, board: BoardKey) -> dict[str, Any]:
    return _named(await boards.seen(None, contests.contest_id_of(scope), board), board)


@router.get(
    f"{CONTEST}/boards",
    operation_id="listBoards",
    summary="The contest's boards the caller sees, each as they see it",
    response_model=list[Board],
)
async def list_boards(session: CurrentSession, scope: ContestAtPath) -> list[dict[str, Any]]:
    """In the order the contest's settings give them; none for anyone but
    staff until audiences come."""
    return _listed(await boards.seen(session, contests.contest_id_of(scope)))


@router.get(
    f"{CONTEST}/boards/{{board}}",
    operation_id="getBoard",
    summary="One of the contest's boards as the caller sees it",
    response_model=Board,
)
async def get_board(
    session: CurrentSession, scope: ContestAtPath, board: BoardKey
) -> dict[str, Any]:
    return _named(await boards.seen(session, contests.contest_id_of(scope), board), board)


@router.get(
    f"{TASK}/marks",
    operation_id="getMyMarks",
    summary="The marks the caller's row holds on the task",
    response_model=Marks,
)
async def get_my_marks(session: CurrentSession, scope: TaskAtPath) -> boards.Marks:
    return await boards.held(session, tasks.task_id_of(scope))


@router.put(
    f"{TASK}/marks/{{number}}",
    operation_id="markSubmission",
    summary="Mark one of the row's own submissions to the task",
    response_model=Marks,
)
async def mark_submission(
    session: CurrentSession, scope: TaskAtPath, number: Number
) -> boards.Marks:
    """Marking a submission already marked changes nothing."""
    return await boards.mark(session, tasks.task_id_of(scope), number)


@router.delete(
    f"{TASK}/marks/{{number}}",
    operation_id="unmarkSubmission",
    summary="Take the mark off one of the row's submissions to the task",
    response_model=Marks,
)
async def unmark_submission(
    session: CurrentSession, scope: TaskAtPath, number: Number
) -> boards.Marks:
    """Taking off a mark the submission does not have changes nothing."""
    return await boards.unmark(session, tasks.task_id_of(scope), number)
