"""The app factory. Configuration is read while the app is built, so a bad value
stops start-up rather than someone's first request.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from importlib.metadata import version

from fastapi import FastAPI

from unicon.api import health
from unicon.api.errors import register_error_handlers
from unicon.api.middleware.origin import OriginCheck
from unicon.api.openapi import build_document
from unicon.api.v1 import router as v1_router
from unicon.db.engine import new_engine, new_probe_engine
from unicon.db.session import new_session_factory
from unicon.forge.admin import AdminClient
from unicon.forge.http import new_forge_http
from unicon.forge.oidc import OidcClient
from unicon.settings import Settings, load_settings


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings: Settings = app.state.settings
    engine = new_engine(settings)
    app.state.engine = engine
    app.state.probe_engine = new_probe_engine(settings)
    app.state.session_factory = new_session_factory(engine)
    forge = new_forge_http(settings)
    app.state.oidc = OidcClient(settings, forge)
    app.state.admin = AdminClient(settings, forge)
    try:
        yield
    finally:
        await forge.aclose()
        await app.state.probe_engine.dispose()
        await engine.dispose()


def create_app(settings: Settings | None = None) -> FastAPI:
    app = FastAPI(
        title="Unicon API",
        version=version("unicon-backend"),
        summary="Contests on top of Forgejo, Woodpecker and Garage",
        lifespan=lifespan,
    )
    config = settings or load_settings()
    app.state.settings = config
    app.add_middleware(OriginCheck, public_url=str(config.public_url))
    register_error_handlers(app)
    app.include_router(health.router)
    app.include_router(v1_router)
    document = build_document(app)
    app.openapi = lambda: document  # type: ignore[method-assign]
    return app
