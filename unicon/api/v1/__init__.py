"""Version 1 of the API. Its fields take the forge's names, so a renamed forge
field renames the answer's field too: the frontend builds against a pinned
copy of `openapi.json` and moves with it in the same change.
"""

from fastapi import APIRouter
from forge.api.types import ScopeKind

from unicon.api.v1 import (
    announcements,
    auth,
    boards,
    clarifications,
    contest_home,
    contestants,
    contests,
    files,
    gradings,
    invites,
    landing,
    live,
    me,
    orgs,
    roles,
    server_time,
    submissions,
    tasks,
    teams,
    uploads,
    workflows,
)

router = APIRouter(prefix="/api/v1")
router.include_router(server_time.router)
router.include_router(auth.router)
router.include_router(me.router)
router.include_router(invites.mine)
router.include_router(orgs.router)
router.include_router(contests.router)
router.include_router(tasks.router)
router.include_router(contestants.router)
router.include_router(teams.router)
router.include_router(contest_home.router)
router.include_router(landing.router)
router.include_router(uploads.router)
router.include_router(submissions.router)
router.include_router(gradings.router)
router.include_router(gradings.feed)
router.include_router(boards.router)
router.include_router(workflows.router)
router.include_router(announcements.reading)
router.include_router(clarifications.router)
router.include_router(live.router)
for kind in ScopeKind:
    router.include_router(roles.router_at(kind))
    router.include_router(invites.router_at(kind))
for kind in (ScopeKind.CONTEST, ScopeKind.TASK):
    router.include_router(files.router_at(kind))
    router.include_router(announcements.router_at(kind))
