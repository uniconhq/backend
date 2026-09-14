"""What the account endpoints answer with."""

from datetime import datetime

from pydantic import BaseModel


class Me(BaseModel):
    user_id: int
    username: str
    name: str | None
    avatar_url: str | None
    email: str | None
    degraded: bool


class SessionInfo(BaseModel):
    id: str

    created_at: datetime
    last_seen_at: datetime
    ip: str | None
    user_agent: str | None
    current: bool
