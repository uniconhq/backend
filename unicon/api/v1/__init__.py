"""Version 1 of the API. Its fields take the forge's names, so a renamed forge
field renames the answer's field too: the frontend builds against a pinned
copy of `openapi.json` and moves with it in the same change.
"""

from fastapi import APIRouter
from forge.api.types import ScopeKind

from unicon.api.v1 import (
    auth,
    contest_home,
    contestants,
    contests,
    files,
    gradings,
    landing,
    me,
    orgs,
    roles,
    server_time,
    submissions,
    tasks,
    uploads,
    workflows,
)

router = APIRouter(prefix="/api/v1")
router.include_router(server_time.router)
router.include_router(auth.router)
router.include_router(me.router)
router.include_router(orgs.router)
router.include_router(contests.router)
router.include_router(tasks.router)
router.include_router(contestants.router)
router.include_router(contest_home.router)
router.include_router(landing.router)
router.include_router(uploads.router)
router.include_router(submissions.router)
router.include_router(gradings.router)
router.include_router(workflows.router)
for kind in ScopeKind:
    router.include_router(roles.router_at(kind))
for kind in (ScopeKind.CONTEST, ScopeKind.TASK):
    router.include_router(files.router_at(kind))
