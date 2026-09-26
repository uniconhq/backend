"""The app factory. The runtime is built while the app starts and stopped when
it stops, so the package's background loops run beside the routes for exactly
as long as the process serves.
"""

from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from importlib.metadata import version

from fastapi import FastAPI
from forge.runtime import Runtime

from unicon.api import health
from unicon.api.errors import register_error_handlers
from unicon.api.middleware.origin import OriginCheck
from unicon.api.middleware.request_log import RequestLog
from unicon.api.openapi import build_document
from unicon.api.v1 import router as v1_router
from unicon.api.v1.auth import CALLBACK_PATH
from unicon.settings import ShellSettings, load_shell_settings

Lifespan = Callable[[FastAPI], AbstractAsyncContextManager[None]]


def create_app(settings: ShellSettings | None = None, runtime: Runtime | None = None) -> FastAPI:
    """Build the app. Without a `runtime`, one is built from the settings when
    the app starts.
    """
    config = settings or load_shell_settings()
    app = FastAPI(
        title="Unicon API",
        version=version("unicon-backend"),
        summary="Contests on top of a git host, a CI and an object store",
        lifespan=_lifespan(config, runtime),
    )
    app.state.settings = config
    app.add_middleware(OriginCheck, public_url=str(config.public_url))
    app.add_middleware(RequestLog)
    register_error_handlers(app)
    app.include_router(health.router)
    app.include_router(v1_router)
    document = build_document(app)
    app.openapi = lambda: document  # type: ignore[method-assign]
    return app


def sign_in_redirect_uri(settings: ShellSettings) -> str:
    """Where the host sends a browser back to after sign-in: this shell's
    callback route on the public URL.
    """
    return str(settings.public_url).rstrip("/") + CALLBACK_PATH


def _lifespan(settings: ShellSettings, given: Runtime | None) -> Lifespan:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        runtime = given or Runtime.build(
            settings, sign_in_redirect_uri=sign_in_redirect_uri(settings)
        )
        app.state.runtime = runtime
        runtime.start_background()
        try:
            yield
        finally:
            await runtime.stop()

    return lifespan
