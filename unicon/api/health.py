"""The two probes, outside `/api/v1`. `/healthz` says the process is up;
`/readyz` says the database answered, on a connection of its own.
"""

import forge.api
from fastapi import APIRouter, Response
from forge.api.errors import NotReady as NotReadyError

from unicon.schemas.health import Health, NotReady, Ready

router = APIRouter(tags=["health"])


@router.get("/healthz", operation_id="getHealth", summary="Is the process up")
async def healthz() -> Health:
    return Health(status="ok")


@router.get(
    "/readyz",
    operation_id="getReadiness",
    summary="Is the database reachable",
    response_model=Ready,
    responses={503: {"model": NotReady, "description": "The database did not answer"}},
)
async def readyz() -> Response | Ready:
    try:
        await forge.api.ready()
    except NotReadyError:
        body = NotReady(status="not_ready")
        return Response(
            status_code=503, content=body.model_dump_json(), media_type="application/json"
        )
    return Ready(status="ready")
