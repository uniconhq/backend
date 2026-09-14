"""Login, callback, logout, and whether this instance takes sign-ups. The frontend
renders no form and never sees a token.
"""

from urllib.parse import urlencode

from fastapi import APIRouter, Query, Request, Response, status
from fastapi.responses import RedirectResponse

from unicon.api import cookies
from unicon.api.deps import Config, CurrentSession, Db, OidcClientDep
from unicon.api.errors import forge_is_down
from unicon.domain.errors import LoginDenied, UniconError
from unicon.forge.errors import ForgeUnreachable
from unicon.schemas.auth import RegisterUrl
from unicon.services import login

FOUND = status.HTTP_302_FOUND
LOGIN_PAGE = "/login"
SIGN_UP_PATH = "/user/sign_up"

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get(
    "/login",
    operation_id="startLogin",
    summary="Start a login through the forge",
    status_code=FOUND,
    response_class=RedirectResponse,
    response_model=None,
)
async def start_login(
    settings: Config,
    oidc: OidcClientDep,
    next: str | None = Query(default=None, description="A path on this site to land on"),
) -> RedirectResponse:
    url, login_cookie = login.start_login(settings, oidc, next)
    response = RedirectResponse(url, status_code=FOUND)
    cookies.set_login(response, login_cookie, settings)
    return response


@router.get(
    "/callback",
    operation_id="completeLogin",
    summary="Land back from the forge",
    status_code=FOUND,
    response_class=RedirectResponse,
    response_model=None,
)
async def complete_login(
    request: Request,
    db: Db,
    settings: Config,
    oidc: OidcClientDep,
    code: str = Query(default=""),
    state: str = Query(default=""),
    error: str | None = Query(default=None),
) -> RedirectResponse:
    login_cookie = request.cookies.get(cookies.LOGIN_COOKIE)
    try:
        if error:
            raise LoginDenied("The forge did not approve this login.")
        session_cookie, next_path = await login.complete_login(
            db,
            settings,
            oidc,
            code=code,
            state=state,
            login_cookie=login_cookie,
            session_cookie=request.cookies.get(cookies.SESSION_COOKIE),
            ip=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    except (UniconError, ForgeUnreachable) as raised:
        failure = raised if isinstance(raised, UniconError) else forge_is_down()
        query = urlencode(
            {"error": failure.code, "next": login.landing_after_failure(settings, login_cookie)}
        )
        response = RedirectResponse(f"{LOGIN_PAGE}?{query}", status_code=FOUND)
        cookies.clear_login(response, settings)
        return response

    response = RedirectResponse(next_path, status_code=FOUND)
    cookies.clear_login(response, settings)
    cookies.set_session(response, session_cookie, settings)
    return response


@router.post(
    "/logout",
    operation_id="logout",
    summary="End this session",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def logout(db: Db, settings: Config, session: CurrentSession) -> Response:
    await login.logout(db, session.id)
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    cookies.clear_session(response, settings)
    return response


@router.get(
    "/register-url",
    operation_id="getRegisterUrl",
    summary="Where to create a forge account, if it is open",
)
async def register_url(settings: Config) -> RegisterUrl:
    if not settings.forge_registration_open:
        return RegisterUrl(url=None)
    return RegisterUrl(url=str(settings.forge_public_url).rstrip("/") + SIGN_UP_PATH)
