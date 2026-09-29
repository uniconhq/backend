"""The package's fixtures come from `forge.testing`, loaded through the
pytest configuration. The tests import `forge.api` and `forge.testing` and
nothing else of the package, as the app does. `served_routes` is every route
the app serves, with the whole path it is served at, since the app holds each
included router as one entry of its own.
"""

import asyncio
import sys
from collections.abc import Callable, Mapping

import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute, iter_route_contexts


def pytest_asyncio_loop_factories(
    config: pytest.Config, item: pytest.Item
) -> Mapping[str, Callable[[], asyncio.AbstractEventLoop]]:
    """psycopg cannot run asynchronously on Windows' default proactor loop."""
    if sys.platform == "win32":
        return {"selector": asyncio.SelectorEventLoop}
    return {"default": asyncio.new_event_loop}


def served_routes(app: FastAPI) -> list[tuple[str, APIRoute]]:
    """Each API route the app serves, with the path it is served at."""
    return [
        (context.path, context.original_route)
        for context in iter_route_contexts(app.routes)
        if isinstance(context.original_route, APIRoute) and context.path is not None
    ]
