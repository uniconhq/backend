"""The committed document is the contract the frontend generates from."""

import json
from pathlib import Path
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from unicon.api.openapi import HTTP_METHODS, build_document
from unicon.main import create_app
from unicon.schemas.problem import PROBLEM_CONTENT_TYPE

COMMITTED_DOCUMENT = Path(__file__).resolve().parents[2] / "openapi.json"


@pytest.fixture
def document() -> dict[str, Any]:
    return build_document(create_app())


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


async def test_the_document_is_served_and_the_api_browsers_are_not() -> None:
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        assert (await client.get("/openapi.json")).status_code == 200
        assert (await client.get("/docs")).status_code == 404
        assert (await client.get("/redoc")).status_code == 404
