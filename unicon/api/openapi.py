"""The OpenAPI document, which is a contract rather than a by-product.
`openapi.json` is committed, CI fails when it is stale, and the frontend
generates its client from a pinned copy.
"""

from typing import Any

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi

from unicon.schemas.problem import PROBLEM_CONTENT_TYPE, Problem

HTTP_METHODS = frozenset({"get", "put", "post", "delete", "options", "head", "patch", "trace"})

FASTAPI_VALIDATION_SCHEMAS = ("HTTPValidationError", "ValidationError")

ERROR_RESPONSE = {
    "description": "An error, as an RFC 9457 problem document. `code` names it.",
    "content": {
        PROBLEM_CONTENT_TYPE: {"schema": {"$ref": "#/components/schemas/Problem"}},
    },
}


def build_document(app: FastAPI) -> dict[str, Any]:
    document = get_openapi(
        title=app.title,
        version=app.version,
        summary=app.summary,
        routes=app.routes,
    )
    schemas = document["components"]["schemas"]
    for name in FASTAPI_VALIDATION_SCHEMAS:
        schemas.pop(name, None)
    _answers_carry_every_field(document)
    schemas["Problem"] = Problem.model_json_schema()
    for operation in _operations(document):
        operation["responses"].pop("422", None)
        operation["responses"]["default"] = ERROR_RESPONSE
    return document


def _operations(document: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        operation
        for operations in document["paths"].values()
        for method, operation in operations.items()
        if method in HTTP_METHODS
    ]


def _answers_carry_every_field(document: dict[str, Any]) -> None:
    """A route's answer is sent whole, a field with a default included, so
    every field of a schema no request body reaches is required. The forge's
    own types give some fields a default, and without this the client would
    read them as fields that may be missing.
    """
    schemas = document["components"]["schemas"]
    bodies = [op["requestBody"] for op in _operations(document) if "requestBody" in op]
    taken = _reached(bodies, schemas)
    for name, schema in schemas.items():
        if name not in taken and "properties" in schema:
            schema["required"] = list(schema["properties"])


def _reached(roots: list[Any], schemas: dict[str, Any]) -> set[str]:
    """The names of the schemas `roots` refer to, directly or through others."""
    found: set[str] = set()
    pending = list(roots)
    while pending:
        node = pending.pop()
        if isinstance(node, dict):
            ref = node.get("$ref")
            name = ref.rsplit("/", 1)[-1] if isinstance(ref, str) else None
            if name is not None and name not in found:
                found.add(name)
                pending.append(schemas.get(name))
            pending.extend(node.values())
        elif isinstance(node, list):
            pending.extend(node)
    return found
