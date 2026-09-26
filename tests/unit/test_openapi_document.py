"""The committed document is the contract the frontend generates from."""

import json
from pathlib import Path
from typing import Any

import pytest

from unicon.api.openapi import HTTP_METHODS, build_document
from unicon.main import create_app
from unicon.schemas.problem import PROBLEM_CONTENT_TYPE
from unicon.settings import ShellSettings

COMMITTED_DOCUMENT = Path(__file__).resolve().parents[2] / "openapi.json"


@pytest.fixture
def document(settings: ShellSettings) -> dict[str, Any]:
    return build_document(create_app(settings))


def _operations(document: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    return [
        (f"{method.upper()} {path}", operation)
        for path, operations in document["paths"].items()
        for method, operation in operations.items()
        if method in HTTP_METHODS
    ]


def test_the_document_is_openapi_31(document: dict[str, Any]) -> None:
    assert document["openapi"].startswith("3.1.")


def test_every_operation_is_named(document: dict[str, Any]) -> None:
    for name, operation in _operations(document):
        assert operation.get("operationId"), name


def test_every_operation_documents_the_problem_document(document: dict[str, Any]) -> None:
    for name, operation in _operations(document):
        error = operation["responses"]["default"]
        assert PROBLEM_CONTENT_TYPE in error["content"], name


def test_the_committed_document_is_current(document: dict[str, Any]) -> None:
    assert json.loads(COMMITTED_DOCUMENT.read_text(encoding="utf-8")) == document
