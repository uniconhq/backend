"""The seam between Unicon and Forgejo. Two clients, split by who they act as:
`Oidc` is the login protocol, `Admin` uses the provisioning token. Calls made
for a person use that person's own token. Forgejo's database is never read
directly.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True)
class TokenSet:
    access_token: str
    refresh_token: str
    expires_at: datetime


@dataclass(frozen=True)
class ForgeIdentity:
    user_id: int

    username: str
    name: str | None
    email: str | None
    avatar_url: str | None


@dataclass(frozen=True)
class TeamMembership:
    org: str
    team: str
    member_count: int


class Oidc(Protocol):
    def authorize_url(self, *, state: str, code_challenge: str, nonce: str) -> str: ...

    async def exchange_code(self, *, code: str, verifier: str) -> TokenSet: ...

    async def refresh(self, refresh_token: str) -> TokenSet: ...

    async def userinfo(self, access_token: str) -> ForgeIdentity: ...


class Admin(Protocol):
    async def username_for(self, user_id: int) -> str: ...

    async def set_active(self, username: str, active: bool) -> None: ...

    async def delete_user(self, username: str) -> None: ...

    async def teams_of(self, username: str) -> list[TeamMembership]: ...
