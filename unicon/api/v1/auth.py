"""Sign-in as HTTP: the redirect to the host, the callback that sets the
session cookie, sign-out, where a person creates an account, and where the
forge's own pages are.
"""

from urllib.parse import urlencode

from fastapi import APIRouter, Query, Request, Response, status
from fastapi.responses import RedirectResponse
from forge.api import sessions, sign_in
from forge.api.errors import SignInDenied, UniconError

from unicon.api import cookies
from unicon.api.deps import CurrentSession
from unicon.schemas.auth import ForgeUrl, RegisterUrl

FOUND = status.HTTP_302_FOUND
NO_CONTENT = status.HTTP_204_NO_CONTENT
SIGN_IN_PAGE = "/login"
CALLBACK_PATH = "/api/v1/auth/callback"

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get(
    "/login",
    operation_id="startLogin",
    summary="Start a sign-in through the forge",
    status_code=FOUND,
    response_class=RedirectResponse,
    response_model=None,
)
async def start_login(
    next: str | None = Query(default=None, description="A path on this site to land on"),
) -> RedirectResponse:
    started = sign_in.start(next)
    response = RedirectResponse(started.url, status_code=FOUND)
    cookies.set_sign_in(response, started.attempt)
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
    code: str = Query(default=""),
    state: str = Query(default=""),
    error: str | None = Query(default=None),
) -> RedirectResponse:
    """The attempt's `next` was made safe by forge when the sign-in started,
    and the attempt comes back signed, so it is used as it is.
    """
    attempt = cookies.read_sign_in(request)
    try:
        if error:
            raise SignInDenied("The forge did not approve this sign-in.")
        session, landing = await sign_in.complete(
            code=code,
            state=state,
            attempt=attempt,
            ip=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
            previous_session_id=cookies.read_session_id(request),
        )
    except UniconError as failure:
        query = urlencode({"error": failure.code, "next": attempt.next if attempt else "/"})
        response = RedirectResponse(f"{SIGN_IN_PAGE}?{query}", status_code=FOUND)
        cookies.clear_sign_in(response)
        return response

    response = RedirectResponse(landing, status_code=FOUND)
    cookies.clear_sign_in(response)
    cookies.set_session(response, session)
    return response


@router.post("/logout", operation_id="logout", summary="End this session", status_code=NO_CONTENT)
async def logout(session: CurrentSession) -> Response:
    await sessions.revoke(session.id)
    response = Response(status_code=NO_CONTENT)
    cookies.clear_session(response)
    return response


@router.get(
    "/register-url",
    operation_id="getRegisterUrl",
    summary="Where to create a forge account, when sign-up is open",
)
async def register_url() -> RegisterUrl:
    return RegisterUrl(url=sign_in.sign_up_url())


@router.get(
    "/forge-url",
    operation_id="getForgeUrl",
    summary="Where a browser reaches the forge's own pages",
)
async def forge_url() -> ForgeUrl:
    """The account lives at the forge, so the app links there for the
    password, the email and two-factor, and signs the browser out there too.
    Served here rather than built into the app, so one image fits every
    deployment.
    """
    return ForgeUrl(url=sign_in.forge_url())
