"""Version 1 of the API. Fields are added, never renamed or removed: the frontend
builds against a pinned copy of `openapi.json`.
"""

from fastapi import APIRouter

from unicon.api.v1 import auth, me, server_time

router = APIRouter(prefix="/api/v1")
router.include_router(server_time.router)
router.include_router(auth.router)
router.include_router(me.router)
