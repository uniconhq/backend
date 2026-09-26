"""Fixtures shared by every test. `Settings.for_tests()` fills in every
variable, so a developer's own environment cannot change what a test sees.
"""

import asyncio
import sys
from collections.abc import Callable, Mapping

import pytest
from forge.settings import Settings


@pytest.fixture
def settings() -> Settings:
    return Settings.for_tests()


def pytest_asyncio_loop_factories(
    config: pytest.Config, item: pytest.Item
) -> Mapping[str, Callable[[], asyncio.AbstractEventLoop]]:
    """psycopg cannot run asynchronously on Windows' default proactor loop."""
    if sys.platform == "win32":
        return {"selector": asyncio.SelectorEventLoop}
    return {"default": asyncio.new_event_loop}
