"""The app factory. Forge is started while the app starts and stopped when it
stops. Building the app reads no setting, so the
OpenAPI document comes out of an app forge was never started for. The
document is served at `/openapi.json`, which the frontend generates from;
the Swagger and ReDoc pages are not, because an API browser is not part of
what a deployment exposes.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from importlib.metadata import version

import forge.api
from fastapi import FastAPI

from unicon.api import door, health
from unicon.api.errors import register_error_handlers
from unicon.api.middleware.origin import OriginCheck
from unicon.api.middleware.request_log import RequestLog
from unicon.api.openapi import build_document
from unicon.api.v1 import events, runs
from unicon.api.v1 import router as v1_router
from unicon.api.v1.auth import CALLBACK_PATH


def create_app() -> FastAPI:
    app = FastAPI(
        title="Unicon API",
        version=version("unicon-backend"),
        summary="Contests on top of a git host, a CI and an object store",
        lifespan=_lifespan,
        docs_url=None,
        redoc_url=None,
    )
    app.add_middleware(OriginCheck)
    app.add_middleware(RequestLog)
    register_error_handlers(app)
    app.include_router(health.router)
    app.include_router(door.router)
    app.include_router(v1_router)
    app.include_router(events.router)
    app.include_router(runs.router)
    document = build_document(app)
    app.openapi = lambda: document  # type: ignore[method-assign]
    return app


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    forge.api.start(callback_path=CALLBACK_PATH)
    try:
        yield
    finally:
        await forge.api.stop()
