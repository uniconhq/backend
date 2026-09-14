"""The calls Unicon makes as itself, with the provisioning token. Never used to
act for a person; that uses the person's own token.
"""

from typing import Any

from unicon.forge.errors import ForgeRejected, ForgeUnreachable
from unicon.forge.http import ForgeHttp
from unicon.forge.protocol import TeamMembership
from unicon.settings import Settings

NOT_FOUND = 404
PAGE_SIZE = 50

MAX_PAGES = 200


class UserNotFound(Exception):
    """Forgejo has no such person: the account was deleted, or the id is wrong."""


class AdminClient:
    def __init__(self, settings: Settings, http: ForgeHttp) -> None:
        self._http = http
        self._headers = {"Authorization": f"token {settings.forge_admin_token.get_secret_value()}"}

    async def username_for(self, user_id: int) -> str:
        found = await self._get(f"/api/v1/users/search?uid={user_id}")
        people = found.get("data") or []
        if not people:
            raise UserNotFound(str(user_id))
        return str(people[0]["login"])

    async def set_active(self, username: str, active: bool) -> None:
        person = await self._get(f"/api/v1/users/{username}")
        await self._http.request(
            "PATCH",
            f"/api/v1/admin/users/{username}",
            headers=self._headers,
            json={
                "active": active,
                "login_name": person.get("login_name") or username,
                "source_id": person.get("source_id", 0),
            },
        )

    async def delete_user(self, username: str) -> None:
        await self._http.request(
            "DELETE", f"/api/v1/admin/users/{username}?purge=false", headers=self._headers
        )

    async def teams_of(self, username: str) -> list[TeamMembership]:
        """Every page of every list: the last-admin rule decides whether an
        account may be deleted.
        """
        memberships: list[TeamMembership] = []
        for org in await self._get_all(f"/api/v1/admin/users/{username}/orgs"):
            org_name = str(org["username"])
            for team in await self._get_all(f"/api/v1/orgs/{org_name}/teams"):
                members = await self._get_all(f"/api/v1/teams/{team['id']}/members")
                logins = {str(member["login"]) for member in members}
                if username in logins:
                    memberships.append(TeamMembership(org_name, str(team["name"]), len(logins)))
        return memberships

    async def _get(self, path: str) -> dict[str, Any]:
        try:
            response = await self._http.request("GET", path, headers=self._headers)
        except ForgeRejected as exc:
            if exc.status == NOT_FOUND:
                raise UserNotFound(path) from exc
            raise
        payload: dict[str, Any] = response.json()
        return payload

    async def _get_all(self, path: str) -> list[dict[str, Any]]:
        """Pages until one comes back empty, not merely short. Forgejo caps
        `limit` at its own maximum, so a short page is not the end of the list.
        """
        collected: list[dict[str, Any]] = []
        for page in range(1, MAX_PAGES + 1):
            separator = "&" if "?" in path else "?"
            response = await self._http.request(
                "GET",
                f"{path}{separator}limit={PAGE_SIZE}&page={page}",
                headers=self._headers,
            )
            batch: list[dict[str, Any]] = response.json()
            if not batch:
                return collected
            collected.extend(batch)
        raise ForgeUnreachable(f"{path} did not end within {MAX_PAGES} pages")
