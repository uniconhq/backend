"""What the account routes answer with."""

from datetime import datetime

from forge.domain.roles import RoleGrant
from forge.services.identity import Me as MeRecord
from forge.services.sessions import SessionInfo as SessionRecord
from pydantic import BaseModel


class Scope(BaseModel):
    kind: str
    org: str
    contest: str | None
    task: str | None


class Role(BaseModel):
    scope: Scope
    role: str

    @classmethod
    def of(cls, grant: RoleGrant) -> Role:
        return cls(
            scope=Scope(
                kind=grant.scope.kind.value,
                org=grant.scope.org,
                contest=grant.scope.contest,
                task=grant.scope.task,
            ),
            role=grant.role.value,
        )


class Me(BaseModel):
    """The signed-in user and their roles at every scope. `degraded` is set
    when the forge did not answer and the identity comes from the session.
    """

    user_id: int
    username: str
    name: str | None
    email: str | None
    avatar_url: str | None
    roles: list[Role]
    degraded: bool

    @classmethod
    def of(cls, me: MeRecord) -> Me:
        return cls(
            user_id=me.user.id,
            username=me.user.username,
            name=me.user.name,
            email=me.user.email,
            avatar_url=me.user.avatar_url,
            roles=[Role.of(grant) for grant in me.roles],
            degraded=me.degraded,
        )


class SessionInfo(BaseModel):
    id: str
    created_at: datetime
    last_seen_at: datetime
    ip: str | None
    user_agent: str | None
    current: bool

    @classmethod
    def of(cls, info: SessionRecord) -> SessionInfo:
        return cls(
            id=info.id.hex,
            created_at=info.created_at,
            last_seen_at=info.last_seen_at,
            ip=str(info.ip) if info.ip else None,
            user_agent=info.user_agent,
            current=info.current,
        )
