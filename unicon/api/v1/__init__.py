"""Version 1 of the API. Fields are added, never renamed or removed: the frontend
builds against a pinned copy of `openapi.json`.
"""

from fastapi import APIRouter
from forge.api.types import ScopeKind

from unicon.api.v1 import auth, contests, files, me, orgs, roles, server_time, tasks

router = APIRouter(prefix="/api/v1")
router.include_router(server_time.router)
router.include_router(auth.router)
router.include_router(me.router)
router.include_router(orgs.router)
router.include_router(contests.router)
router.include_router(tasks.router)
for kind in ScopeKind:
    router.include_router(roles.router_at(kind))
for kind in (ScopeKind.CONTEST, ScopeKind.TASK):
    router.include_router(files.router_at(kind))
