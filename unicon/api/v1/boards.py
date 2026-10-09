"""The contest's boards and the marks a row holds for its `marked` boards.

A board is read as the reader's audience sees it: a visitor under
`/public`, with no cookie, sees the boards for `everyone`; a signed-in
person sees those their audience may, each cut to the rows its `rows` gives
them. Organisers with the observer role at the contest read every board
`now` and `final`, every row given, and may pick a row, a contestant by
`user_id` or a team by `team`, to read `now` as that row does. A board the
reader may not see is no such board, the same as one that is not there.

A contestant reads, marks and unmarks their row's own submissions to a task
with a session alone; forge checks the submission is the row's, the task
has marks, how many the row may hold and that its close has not passed,
answering `marks_off`, `mark_limit` with `limit` and `marks_frozen`.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query
from forge.api import boards, contests, tasks
from forge.api.access import Organiser
from forge.api.boards import TeamOwner, UserOwner
from forge.api.errors import NotFound, Rejected
from forge.api.types import Role, ScopeKind

from unicon.api.deps import CurrentSession
from unicon.api.guard import PREFIX, ContestAtPath, TaskAtPath, require
from unicon.api.v1.submissions import Number
from unicon.schemas.boards import Board, Marks, OrganisedBoard

CONTEST = PREFIX[ScopeKind.CONTEST]
TASK = PREFIX[ScopeKind.TASK]
PUBLIC = "/public/contests/{org}/{contest}"
NO_SUCH_BOARD = "No such board."

router = APIRouter(tags=["boards"])

ContestObserver = Annotated[Organiser, Depends(require(Role.OBSERVER, ScopeKind.CONTEST))]
BoardName = Annotated[str, Path(description="The board's `name`")]


def _named(found: tuple[boards.Standings, ...], board: str) -> boards.Standings:
    for standings in found:
        if standings.board.name == board:
            return standings
    raise NotFound(NO_SUCH_BOARD)


@router.get(
    f"{PUBLIC}/boards",
    operation_id="listPublicBoards",
    summary="The boards of a public contest that everyone sees",
    response_model=list[Board],
    tags=["public"],
)
async def list_public_boards(scope: ContestAtPath) -> tuple[boards.Standings, ...]:
    """In the order the contest's settings give them."""
    return await boards.seen(None, contests.contest_id_of(scope))


@router.get(
    f"{PUBLIC}/boards/{{board}}",
    operation_id="getPublicBoard",
    summary="One board of a public contest that everyone sees",
    response_model=Board,
    tags=["public"],
)
async def get_public_board(scope: ContestAtPath, board: BoardName) -> boards.Standings:
    return _named(await boards.seen(None, contests.contest_id_of(scope), board), board)


@router.get(
    f"{CONTEST}/boards",
    operation_id="listBoards",
    summary="The contest's boards the caller sees, each as they see it",
    response_model=list[Board],
)
async def list_boards(
    session: CurrentSession, scope: ContestAtPath
) -> tuple[boards.Standings, ...]:
    """In the order the contest's settings give them."""
    return await boards.seen(session, contests.contest_id_of(scope))


@router.get(
    f"{CONTEST}/boards/{{board}}",
    operation_id="getBoard",
    summary="One of the contest's boards as the caller sees it",
    response_model=Board,
)
async def get_board(
    session: CurrentSession, scope: ContestAtPath, board: BoardName
) -> boards.Standings:
    return _named(await boards.seen(session, contests.contest_id_of(scope), board), board)


@router.get(
    f"{CONTEST}/organise/boards",
    operation_id="listOrganisedBoards",
    summary="Every board of the contest, now and final, with what it asks that does not hold",
    response_model=list[OrganisedBoard],
)
async def list_organised_boards(
    organiser: ContestObserver,
    user_id: Annotated[
        int | None, Query(description="Read `now` as this contestant's row does")
    ] = None,
    team: Annotated[uuid.UUID | None, Query(description="Read `now` as this team does")] = None,
) -> tuple[boards.OrganisedBoard, ...]:
    """Every row on both, unless a row is picked: then only the boards that
    row sees, `now` as it sees it, its own row and the rows its `rows`
    gives. A row is a contestant or a team, never both; one that is not a
    row of the contest is not found.
    """
    if user_id is not None and team is not None:
        raise Rejected("Pick a contestant or a team, not both.")
    row: UserOwner | TeamOwner | None = None
    if user_id is not None:
        row = UserOwner(user_id)
    elif team is not None:
        row = TeamOwner(team)
    return await boards.organised(organiser, contests.contest_id_of(organiser.scope), row)


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
