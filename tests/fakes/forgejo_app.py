"""A Forgejo-shaped HTTP server, so the real clients can be tested against
something. It answers the endpoints Task 2 uses with the shapes Forgejo 15
uses, over the `FakeForge` state.
"""

import asyncio
from datetime import UTC, datetime
from typing import Any
from urllib.parse import parse_qsl, urlencode

import httpx
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse, Response
from starlette.routing import Route

from tests.fakes.forge import FakeForge, FakeUser
from unicon.forge.errors import ForgeRejected, ForgeTokenExpired

ADMIN_TOKEN = "fake-admin-token"
GRANT_TYPES = frozenset({"authorization_code", "refresh_token"})
BAD_REQUEST = 400


def forgejo_app(forge: FakeForge) -> Starlette:
    async def authorize(request: Request) -> Response:
        """The consent page, with the person already decided by the test."""
        query = request.query_params
        code = forge.authorize(forge.signed_in_user_id, query["code_challenge"])
        landing = query["redirect_uri"]
        return RedirectResponse(
            f"{landing}?{urlencode({'code': code, 'state': query['state']})}", status_code=302
        )

    async def token(request: Request) -> Response:
        form = dict(parse_qsl((await request.body()).decode()))
        if form.get("client_id") != forge.client_id:
            return _oauth_error("invalid_client", "client id is not registered")
        if form.get("client_secret") != forge.client_secret:
            return _oauth_error("invalid_client", "client secret does not match")
        grant = form.get("grant_type", "")
        if grant not in GRANT_TYPES:
            return _oauth_error("unsupported_grant_type", f"{grant} is not offered")
        try:
            if grant == "refresh_token":
                await asyncio.sleep(forge.refresh_delay)
                issued = forge.spend_refresh(form.get("refresh_token", ""))
            else:
                if form.get("redirect_uri") != forge.redirect_uri:
                    return _oauth_error("invalid_request", "redirect_uri does not match")
                issued = forge.spend_code(form.get("code", ""), form.get("code_verifier", ""))
        except ForgeTokenExpired:
            return _oauth_error("unauthorized_client", "refresh token is not accepted")
        except ForgeRejected:
            return _oauth_error("invalid_grant", "the authorization code is not accepted")
        return JSONResponse(
            {
                "access_token": issued.access_token,
                "refresh_token": issued.refresh_token,
                "token_type": "bearer",
                "expires_in": int((issued.expires_at - datetime.now(UTC)).total_seconds()),
            }
        )

    async def userinfo(request: Request) -> Response:
        header = request.headers.get("authorization", "")
        try:
            identity = forge.identity_for(header.removeprefix("Bearer "))
        except ForgeRejected as exc:
            return JSONResponse({"error": exc.body}, status_code=exc.status)
        return JSONResponse(
            {
                "sub": str(identity.user_id),
                "preferred_username": identity.username,
                "name": identity.name,
                "email": identity.email,
                "picture": identity.avatar_url,
                "groups": [],
            }
        )

    async def search_users(request: Request) -> Response:
        person = forge.users.get(int(request.query_params["uid"]))
        return JSONResponse({"data": [_user_json(person)] if person else []})

    async def get_user(request: Request) -> Response:
        return _person(forge, request, lambda person: JSONResponse(_user_json(person)))

    async def patch_user(request: Request) -> Response:
        if not _is_admin(request):
            return JSONResponse({"message": "token required"}, status_code=401)
        if forge.refusal is not None:
            return JSONResponse({"message": forge.refusal}, status_code=422)
        body = await request.json()
        if "login_name" not in body or "source_id" not in body:
            return JSONResponse({"message": "login_name is required"}, status_code=422)

        def apply(person: FakeUser) -> Response:
            person.active = bool(body["active"])
            return JSONResponse(_user_json(person))

        return _person(forge, request, apply)

    async def delete_user(request: Request) -> Response:
        if not _is_admin(request):
            return JSONResponse({"message": "token required"}, status_code=401)
        if forge.refusal is not None:
            return JSONResponse({"message": forge.refusal}, status_code=422)

        def remove(person: FakeUser) -> Response:
            del forge.users[person.user_id]
            return Response(status_code=204)

        return _person(forge, request, remove)

    async def user_orgs(request: Request) -> Response:
        orgs = sorted({team.org for team in forge.teams})
        return JSONResponse(_page(request, forge, [{"username": org} for org in orgs]))

    async def org_teams(request: Request) -> Response:
        org = request.path_params["org"]
        teams = [
            {"id": index, "name": team.name}
            for index, team in enumerate(forge.teams)
            if team.org == org
        ]
        return JSONResponse(_page(request, forge, teams))

    async def team_members(request: Request) -> Response:
        team = forge.teams[int(request.path_params["team_id"])]
        return JSONResponse(_page(request, forge, [{"login": member} for member in team.members]))

    return Starlette(
        routes=[
            Route("/login/oauth/authorize", authorize),
            Route("/login/oauth/access_token", token, methods=["POST"]),
            Route("/login/oauth/userinfo", userinfo),
            Route("/api/v1/users/search", search_users),
            Route("/api/v1/users/{username}", get_user),
            Route("/api/v1/admin/users/{username}", patch_user, methods=["PATCH"]),
            Route("/api/v1/admin/users/{username}", delete_user, methods=["DELETE"]),
            Route("/api/v1/admin/users/{username}/orgs", user_orgs),
            Route("/api/v1/orgs/{org}/teams", org_teams),
            Route("/api/v1/teams/{team_id}/members", team_members),
        ]
    )


class SwitchableTransport(httpx.AsyncBaseTransport):
    """Carries requests to the fake app, or refuses to connect while
    `forge.unreachable` is set, which is what a stopped Forgejo looks like.
    """

    def __init__(self, forge: FakeForge, app: Starlette) -> None:
        self._forge = forge
        self._inner = httpx.ASGITransport(app=app)

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        if self._forge.unreachable:
            raise httpx.ConnectError("connection refused", request=request)
        return await self._inner.handle_async_request(request)


def _oauth_error(error: str, description: str) -> Response:
    """RFC 6749's shape, which is what Forgejo answers with."""
    return JSONResponse({"error": error, "error_description": description}, status_code=BAD_REQUEST)


def _page(request: Request, forge: FakeForge, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Forgejo pages its list endpoints. `limit` is clamped the way Forgejo clamps
    it, so a page is short whenever the client asked for more than the instance
    allows, not only at the end of a list.
    """
    limit = min(int(request.query_params.get("limit", 30)), forge.max_response_items)
    page = int(request.query_params.get("page", 1))
    start = (page - 1) * limit
    return items[start : start + limit]


def _person(forge: FakeForge, request: Request, act: Any) -> Response:
    username = request.path_params["username"]
    person = next((one for one in forge.users.values() if one.username == username), None)
    if person is None:
        return JSONResponse({"message": "user does not exist"}, status_code=404)
    result: Response = act(person)
    return result


def _user_json(person: FakeUser) -> dict[str, Any]:
    return {
        "id": person.user_id,
        "login": person.username,
        "login_name": "",
        "source_id": 0,
        "full_name": person.name,
        "email": person.email,
        "avatar_url": person.avatar_url,
        "active": person.active,
    }


def _is_admin(request: Request) -> bool:
    return request.headers.get("authorization") == f"token {ADMIN_TOKEN}"
