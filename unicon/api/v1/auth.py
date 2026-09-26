"""Sign-in as HTTP: the redirect to the host, the callback that sets the
session cookie, sign-out, and where a person creates an account.
"""

from urllib.parse import urlencode

from fastapi import APIRouter, Query, Request, Response, status
from fastapi.responses import RedirectResponse
from forge.domain.errors import SignInDenied, UniconError
from forge.domain.next_path import safe_next
from forge.services import sessions, sign_in

from unicon.api import cookies
from unicon.api.deps import Config, Ctx, CurrentSession
from unicon.schemas.auth import RegisterUrl

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
    settings: Config,
    ctx: Ctx,
    next: str | None = Query(default=None, description="A path on this site to land on"),
) -> RedirectResponse:
    started = sign_in.start(ctx.forge, next)
    response = RedirectResponse(started.url, status_code=FOUND)
    cookies.set_sign_in(response, started.attempt, settings)
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
    settings: Config,
    ctx: Ctx,
    code: str = Query(default=""),
    state: str = Query(default=""),
    error: str | None = Query(default=None),
) -> RedirectResponse:
    attempt = cookies.read_sign_in(request, settings)
    try:
        if error:
            raise SignInDenied("The forge did not approve this sign-in.")
        session, landing = await sign_in.complete(
            ctx,
            code=code,
            state=state,
            attempt=attempt,
            ip=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    except UniconError as failure:
        landing = safe_next(attempt.next) if attempt else "/"
        query = urlencode({"error": failure.code, "next": landing})
        response = RedirectResponse(f"{SIGN_IN_PAGE}?{query}", status_code=FOUND)
        cookies.clear_sign_in(response, settings)
        return response

    previous = cookies.read_session_id(request, settings)
    if previous is not None:
        await sessions.revoke(ctx, previous)
    response = RedirectResponse(landing, status_code=FOUND)
    cookies.clear_sign_in(response, settings)
    cookies.set_session(response, session.id, settings)
    return response


@router.post("/logout", operation_id="logout", summary="End this session", status_code=NO_CONTENT)
async def logout(settings: Config, ctx: Ctx, session: CurrentSession) -> Response:
    await sessions.revoke(ctx, session.id)
    response = Response(status_code=NO_CONTENT)
    cookies.clear_session(response, settings)
    return response


@router.get(
    "/register-url",
    operation_id="getRegisterUrl",
    summary="Where to create a forge account, when sign-up is open",
)
async def register_url(ctx: Ctx) -> RegisterUrl:
    return RegisterUrl(url=ctx.forge.identity.sign_up_url())
