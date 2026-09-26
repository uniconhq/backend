"""The package's fixtures come from `forge.testing`, loaded through the
pytest configuration; the shell's settings replace the package's so the
cookie key is present.
"""

import asyncio
import sys
from collections.abc import Callable, Mapping

import pytest
from forge.testing import APP_URL, FORGE_URL

from unicon.settings import ShellSettings


@pytest.fixture
def settings(request: pytest.FixtureRequest) -> ShellSettings:
    """The shell's settings, over a migrated database when the test asks for
    one and over no database otherwise.
    """
    overrides = {"public_url": APP_URL, "forge_public_url": FORGE_URL}
    if "migrated_database_url" in request.fixturenames:
        overrides["database_url"] = request.getfixturevalue("migrated_database_url")
    return ShellSettings.for_tests(**overrides)


def pytest_asyncio_loop_factories(
    config: pytest.Config, item: pytest.Item
) -> Mapping[str, Callable[[], asyncio.AbstractEventLoop]]:
    """psycopg cannot run asynchronously on Windows' default proactor loop."""
    if sys.platform == "win32":
        return {"selector": asyncio.SelectorEventLoop}
    return {"default": asyncio.new_event_loop}
