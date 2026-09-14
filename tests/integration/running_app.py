"""An app with its lifespan running. httpx speaks ASGI but does not run lifespan
events, and without them `app.state.engine` never exists.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from unicon.main import create_app
from unicon.settings import Settings


@asynccontextmanager
async def running_app(settings: Settings) -> AsyncIterator[FastAPI]:
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        yield app
