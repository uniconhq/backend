"""Server time. The UI trusts no other clock for deadlines."""

from datetime import UTC, datetime

from fastapi import APIRouter

from unicon.schemas.server_time import ServerTime

router = APIRouter(tags=["time"])


@router.get("/time", operation_id="getServerTime", summary="Server time in UTC")
async def get_server_time() -> ServerTime:
    return ServerTime(now=datetime.now(UTC))
