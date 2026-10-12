"""What a signed-in person reads of the contests they may see: the list of
them, a contest's home and a task's page. Each needs a session and no role;
forge applies the contest's visibility and the release rules, and a contest
or task the caller may not see answers as not found, the same as one that is
not there.

A task's public files, the ones under its `public/` such as a statement's
images, are served one by one by their path under `public/`, as the task's
latest publication holds them, to whoever may read its statement: a visitor
with no session, or one whose session has ended, as `/public` serves the
statement; a signed-in person who reads the task's page; and whoever holds
a role reaching the task, released or not. The answer is the file's bytes,
typed by its ending, with nothing for a browser to guess, and an SVG opened
on its own runs no script. A file larger than a page is served is
`public_file_too_large`, with the `limit` in bytes.
"""

import hashlib
from http import HTTPStatus
from typing import Final

from fastapi import APIRouter, Request, Response
from forge.api import contest_home, contests, landing, tasks
from forge.api.types import ScopeKind

from unicon.api.deps import CurrentSession, OptionalSession
from unicon.api.guard import PREFIX, ContestAtPath, TaskAtPath
from unicon.schemas.contest_home import ContestHome, ContestSummary, TaskPage

CONTEST = PREFIX[ScopeKind.CONTEST]
TASK = PREFIX[ScopeKind.TASK]
PUBLIC = "public/"
IMAGE_TYPES: Final = {
    ".apng": "image/apng",
    ".avif": "image/avif",
    ".bmp": "image/bmp",
    ".gif": "image/gif",
    ".ico": "image/x-icon",
    ".jpeg": "image/jpeg",
    ".jpg": "image/jpeg",
    ".png": "image/png",
    ".svg": "image/svg+xml",
    ".webp": "image/webp",
}
"""The type a public file is served as, by its ending; any other is
`OTHER_TYPE`."""
OTHER_TYPE = "application/octet-stream"
SVG = "image/svg+xml"
PUBLIC_HEADERS: Final = {
    "X-Content-Type-Options": "nosniff",
    "Cache-Control": "private, no-cache",
}
"""Kept by the reader's browser alone, and asked again each time with its
tag, so a picture a save replaced shows at once, on an organiser's preview
as on an entrant's page; one unchanged costs no bytes (304)."""
SVG_POLICY = "default-src 'none'; style-src 'unsafe-inline'; sandbox"

router = APIRouter(tags=["contest home"])


@router.get(
    "/contests",
    operation_id="listMyContests",
    summary="Every published contest the caller may enter or has entered",
    response_model=list[ContestSummary],
)
async def list_my_contests(session: CurrentSession) -> tuple[contest_home.ContestSummary, ...]:
    """Newest start first, each with the status of the caller's entrant. An
    organiser finds their own contests from their orgs.
    """
    return await contest_home.contests(session)


@router.get(
    f"{CONTEST}/home",
    operation_id="getContestHome",
    summary="The contest's home",
    response_model=ContestHome,
)
async def get_contest_home(
    session: CurrentSession, scope: ContestAtPath
) -> contest_home.ContestHome:
    """The contest's dates, the caller's registration panel, the server's
    clock, and the tasks released to the caller, each with when it falls
    due and closes for their entrant.
    """
    return await contest_home.home(session, contests.contest_id_of(scope))


@router.get(
    f"{TASK}/page",
    operation_id="getTaskPage",
    summary="A released task's page",
    response_model=TaskPage,
)
async def get_task_page(session: CurrentSession, scope: TaskAtPath) -> contest_home.TaskPage:
    """The statement, the caps a submit is counted against, the form of the
    inputs a contestant gives, and when it falls due and closes for the
    caller.
    """
    return await contest_home.task(session, tasks.task_id_of(scope))


@router.get(
    f"{TASK}/public/{{path:path}}",
    operation_id="getTaskPublicFile",
    summary="A file under a task's public/, such as a statement's image",
    response_class=Response,
    responses={
        200: {
            "description": "The file's bytes, typed by its ending.",
            "content": {
                kind: {"schema": {"type": "string", "format": "binary"}}
                for kind in sorted({*IMAGE_TYPES.values(), OTHER_TYPE})
            },
        }
    },
)
async def get_task_public_file(
    session: OptionalSession, scope: TaskAtPath, path: str, request: Request
) -> Response:
    """`path` is the file's path under `public/`. Read with exactly the rights
    the statement is read with, as the task's latest publication holds it,
    and, for a signed-in caller holding a role reaching the task, whether or
    not it is released, as the task's head holds it, the draft the
    statement's preview draws. Each answer carries an `ETag` of its bytes
    and is asked again each time; `If-None-Match` with that tag is answered
    304 while the bytes are the same. A path with an empty,
    `.` or `..` segment, or a file that is not there, is `not_found`, the
    same as a task the caller may not read; one larger than a page is served
    is `public_file_too_large`, with the `limit` in bytes.
    """
    task = tasks.task_id_of(scope)
    named = f"{PUBLIC}{path}"
    found = await (
        contest_home.public_file(session, task, named)
        if session is not None
        else landing.public_file(task, named)
    )
    kind = content_type_of(found.path)
    headers = {**PUBLIC_HEADERS, "ETag": f'"{hashlib.sha256(found.content).hexdigest()}"'}
    if kind == SVG:
        headers["Content-Security-Policy"] = SVG_POLICY
    if headers["ETag"] in _tags(request.headers.get("if-none-match")):
        return Response(status_code=HTTPStatus.NOT_MODIFIED, headers=headers)
    return Response(content=found.content, media_type=kind, headers=headers)


def _tags(asked: str | None) -> set[str]:
    """The tags an `If-None-Match` names, weak ones as their strong form."""
    if not asked:
        return set()
    return {tag.strip().removeprefix("W/") for tag in asked.split(",") if tag.strip()}


def content_type_of(path: str) -> str:
    """The type a public file is served as: a common image type by its
    ending, in any case, and `OTHER_TYPE` for anything else.
    """
    name = path.rsplit("/", 1)[-1]
    ending = name[name.rfind(".") :].lower() if "." in name else ""
    return IMAGE_TYPES.get(ending, OTHER_TYPE)
