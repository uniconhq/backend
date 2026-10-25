"""The contest's leaderboards, each as the caller reads it.

Each leaderboard answers per caller. Someone with the observer role at the
contest reads every leaderboard, every row and cell, with no hold. Anyone else
reads each leaderboard whose audience lets them: `everyone`, a visitor under
`/public` included; `entrants`, a member of an approved entrant. A leaderboard
they may not read is left out of the list, and as one leaderboard is no such
leaderboard, the same as one that is not there. They read each row's values as
that row's entrant is shown them, a cell that read anything else hidden,
the rows cut to the leaderboard's `rows`, and, while the contest's hold holds,
every row but their own counting only its submissions made before the
hold's `from`, each with its values as they stand now, with how many of
its submissions are held.
"""

from typing import Annotated, Any

from fastapi import APIRouter, Path
from forge.api import contests, leaderboards
from forge.api.errors import NotFound
from forge.api.types import ScopeKind

from unicon.api.deps import CurrentSession
from unicon.api.guard import PREFIX, ContestAtPath
from unicon.schemas.leaderboards import Leaderboard, leaderboard_of

CONTEST = PREFIX[ScopeKind.CONTEST]
PUBLIC = "/public/contests/{org}/{contest}"
NO_SUCH_LEADERBOARD = "There is no such leaderboard."

router = APIRouter(tags=["leaderboards"])

LeaderboardKey = Annotated[str, Path(description="The leaderboard's key in `leaderboards`")]


def _listed(found: tuple[leaderboards.LeaderboardView, ...]) -> list[dict[str, Any]]:
    return [leaderboard_of(each) for each in found]


def _named(found: tuple[leaderboards.LeaderboardView, ...], leaderboard: str) -> dict[str, Any]:
    for each in found:
        if each.key == leaderboard:
            return leaderboard_of(each)
    raise NotFound(NO_SUCH_LEADERBOARD)


@router.get(
    f"{PUBLIC}/leaderboards",
    operation_id="listPublicLeaderboards",
    summary="The leaderboards of a public contest that everyone sees",
    response_model=list[Leaderboard],
    tags=["public"],
)
async def list_public_leaderboards(scope: ContestAtPath) -> list[dict[str, Any]]:
    """Those for `everyone`, each as a visitor reads it."""
    return _listed(await leaderboards.seen(None, contests.contest_id_of(scope)))


@router.get(
    f"{PUBLIC}/leaderboards/{{leaderboard}}",
    operation_id="getPublicLeaderboard",
    summary="One leaderboard of a public contest that everyone sees",
    response_model=Leaderboard,
    tags=["public"],
)
async def get_public_leaderboard(
    scope: ContestAtPath, leaderboard: LeaderboardKey
) -> dict[str, Any]:
    return _named(
        await leaderboards.seen(None, contests.contest_id_of(scope), leaderboard), leaderboard
    )


@router.get(
    f"{CONTEST}/leaderboards",
    operation_id="listLeaderboards",
    summary="The contest's leaderboards the caller sees, each as they see it",
    response_model=list[Leaderboard],
)
async def list_leaderboards(session: CurrentSession, scope: ContestAtPath) -> list[dict[str, Any]]:
    """In the order the contest's settings give them."""
    return _listed(await leaderboards.seen(session, contests.contest_id_of(scope)))


@router.get(
    f"{CONTEST}/leaderboards/{{leaderboard}}",
    operation_id="getLeaderboard",
    summary="One of the contest's leaderboards as the caller sees it",
    response_model=Leaderboard,
)
async def get_leaderboard(
    session: CurrentSession, scope: ContestAtPath, leaderboard: LeaderboardKey
) -> dict[str, Any]:
    return _named(
        await leaderboards.seen(session, contests.contest_id_of(scope), leaderboard), leaderboard
    )
