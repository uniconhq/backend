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
    schemas["Problem"] = Problem.model_json_schema()
    for name in FASTAPI_VALIDATION_SCHEMAS:
        schemas.pop(name, None)
    for operations in document["paths"].values():
        for method, operation in operations.items():
            if method in HTTP_METHODS:
                operation["responses"].pop("422", None)
                operation["responses"]["default"] = ERROR_RESPONSE
    return document
