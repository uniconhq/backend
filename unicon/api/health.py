"""The two probes, outside `/api/v1` because they are not part of the API.
`/readyz` checks Postgres and nothing else, on a connection of its own, so a
backend with a full pool answers ready rather than dead.
"""

from fastapi import APIRouter, Request, Response

from unicon.db.engine import ping
from unicon.schemas.health import Health, NotReady, Ready

READY_TIMEOUT_SECONDS = 2.0

router = APIRouter(tags=["health"])


@router.get("/healthz", operation_id="getHealth", summary="Is the process up")
async def healthz() -> Health:
    return Health(status="ok")


@router.get(
    "/readyz",
    operation_id="getReadiness",
    summary="Is Postgres reachable",
    response_model=Ready,
    responses={503: {"model": NotReady, "description": "Postgres did not answer"}},
)
async def readyz(request: Request) -> Response | Ready:
    try:
        await ping(request.app.state.probe_engine, READY_TIMEOUT_SECONDS)
    except Exception as exc:
        body = NotReady(status="not_ready", postgres=type(exc).__name__)
        return Response(
            status_code=503,
            content=body.model_dump_json(),
            media_type="application/json",
        )
    return Ready(status="ready")
