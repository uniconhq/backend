"""Making an account and making an org past the setting are the operator's,
from the command line, and no route reaches either.
"""

import inspect
import re
import sys
from pathlib import Path

from forge.api import account, orgs

from tests.conftest import served_routes
from unicon.main import create_app

API = Path(__file__).resolve().parents[2] / "unicon" / "api"
OPERATOR_ONLY = re.compile(r"\baccount\.create\b|\bcreate_by_operator\b")


def test_no_route_holds_an_operator_action() -> None:
    modules = {sys.modules[route.endpoint.__module__] for _, route in served_routes(create_app())}

    assert modules
    for module in modules:
        assert str(API) in str(inspect.getfile(module)), module.__name__
        assert account.create not in vars(module).values(), module.__name__
        assert orgs.create_by_operator not in vars(module).values(), module.__name__


def test_no_module_under_the_api_names_an_operator_action() -> None:
    for source in API.rglob("*.py"):
        assert not OPERATOR_ONLY.search(source.read_text(encoding="utf-8")), source.name
