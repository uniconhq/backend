"""A Forgejo that runs in this process, so tests can push it into states a real
one reaches rarely: refusing a refresh token, being unreachable, being the only
admin of a team. `forgejo_app.py` puts this state behind HTTP. It lives under
`tests/` so the production image ships no fakes.
"""

import json
import secrets
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from unicon.auth.pkce import challenge_for
from unicon.forge.admin import UserNotFound
from unicon.forge.errors import ForgeRejected, ForgeTokenExpired, ForgeUnreachable
from unicon.forge.protocol import ForgeIdentity, TeamMembership, TokenSet

ACCESS_TOKEN_TTL = timedelta(hours=1)

BAD_REQUEST = 400
UNPROCESSABLE = 422


@dataclass
class FakeUser:
    user_id: int
    username: str
    name: str | None = None
    email: str | None = None
    avatar_url: str | None = None
    active: bool = True


@dataclass
class FakeTeam:
    org: str
    name: str
    members: list[str]


@dataclass
class FakeForge:
    client_id: str = "test-client-id"
    client_secret: str = "test-client-secret"
    redirect_uri: str = "http://app.test/api/v1/auth/callback"

    max_response_items: int = 50

    users: dict[int, FakeUser] = field(default_factory=dict)
    teams: list[FakeTeam] = field(default_factory=list)
    codes: dict[str, tuple[int, str]] = field(default_factory=dict)
    access_tokens: dict[str, int] = field(default_factory=dict)
    refresh_tokens: dict[str, int] = field(default_factory=dict)

    signed_in_user_id: int = 0

    unreachable: bool = False

    refuse_refresh: bool = False
    refreshes: int = 0

    refresh_delay: float = 0.0

    refusal: str | None = None

    def add_user(
        self,
        user_id: int,
        username: str,
        *,
        name: str | None = None,
        email: str | None = None,
        avatar_url: str | None = None,
    ) -> FakeUser:
        person = FakeUser(user_id, username, name, email, avatar_url)
        self.users[user_id] = person
        return person

    def by_username(self, username: str) -> FakeUser:
        for person in self.users.values():
            if person.username == username:
                return person
        raise UserNotFound(username)

    def authorize(self, user_id: int, code_challenge: str) -> str:
        """What the person's browser does on the consent page."""
        code = secrets.token_urlsafe(16)
        self.codes[code] = (user_id, code_challenge)
        return code

    def spend_code(self, code: str, verifier: str) -> TokenSet:
        entry = self.codes.pop(code, None)
        if entry is None:
            raise ForgeRejected(BAD_REQUEST, "invalid code")
        user_id, challenge = entry
        if challenge_for(verifier) != challenge:
            raise ForgeRejected(BAD_REQUEST, "invalid code_verifier")
        return self.mint(user_id)

    def mint(self, user_id: int, ttl: timedelta = ACCESS_TOKEN_TTL) -> TokenSet:
        access, refresh = secrets.token_urlsafe(16), secrets.token_urlsafe(16)
        self.access_tokens[access] = user_id
        self.refresh_tokens[refresh] = user_id
        return TokenSet(access, refresh, datetime.now(UTC) + ttl)

    def spend_refresh(self, refresh_token: str) -> TokenSet:
        if self.refuse_refresh:
            raise ForgeTokenExpired("refused")
        user_id = self.refresh_tokens.pop(refresh_token, None)
        if user_id is None:
            raise ForgeTokenExpired("unknown refresh token")
        self.refreshes += 1
        return self.mint(user_id)

    def identity_for(self, access_token: str) -> ForgeIdentity:
        user_id = self.access_tokens.get(access_token)
        if user_id is None:
            raise ForgeRejected(401, "unknown token")
        person = self.users[user_id]
        return ForgeIdentity(
            user_id=person.user_id,
            username=person.username,
            name=person.name,
            email=person.email,
            avatar_url=person.avatar_url,
        )

    def memberships_of(self, username: str) -> list[TeamMembership]:
        return [
            TeamMembership(team.org, team.name, len(team.members))
            for team in self.teams
            if username in team.members
        ]

    def check_reachable(self) -> None:
        if self.unreachable:
            raise ForgeUnreachable("the fake forge is switched off")

    def check_willing(self) -> None:
        if self.refusal is not None:
            raise ForgeRejected(UNPROCESSABLE, json.dumps({"message": self.refusal}))
