"""What a signed-in person reads of the contests they may see: the list of
them, a contest's home and a task's page. Each needs a session and no role;
forge applies the contest's visibility and the release rules, and a contest
or task the caller may not see answers as not found, the same as one that is
not there.

A task's public files, the ones under its `public/`, such as a statement's
images, are served with its statement, one by one by their path under
`public/`, as the task's latest publication holds them, to whoever may read
its statement: a visitor
with no session, or one whose session has ended, as `/public` serves the
statement; a signed-in person who reads the task's page; and whoever holds
a role reaching the task, released or not. The answer is the file's bytes,
typed by its ending, with nothing for a browser to guess, and an SVG opened
on its own runs no script. A file larger than a page is served is
`public_file_too_large`, with the `limit` in bytes.

An input the task's `show` shows that is a file or a folder, a setting
under `inputs` or a run's own input under a run entry, is fetched by the
same readers, while it is shown at a moment that has come: its route
answers with each file's address at the download door
(`unicon/api/door.py`), which serves it whole whatever its size, so its
bytes never pass through here. A setting is named by its name, and a run's
input by the entry's `of`, the run's place there and the input's name, as
the task's page lists them; anything not shown now is `not_found`, the
same as one that is not there.
"""

import hashlib
from http import HTTPStatus
from typing import Annotated, Final
from urllib.parse import quote

from fastapi import APIRouter, Path, Request, Response
from forge.api import contest_home, contests, landing, tasks
from forge.api.contest_home import ShownInput
from forge.api.types import ScopeKind

from unicon.api.deps import CurrentSession, OptionalSession
from unicon.api.downloads import INPUTS, RUNS, quoted, task_downloads
from unicon.api.guard import PREFIX, ContestAtPath, TaskAtPath
from unicon.schemas.contest_home import (
    ContestHome,
    ContestSummary,
    ShownFile,
    ShownInputFiles,
    TaskPage,
)
from unicon.schemas.contests import Pictures
from unicon.schemas.submissions import NUMBER_MAX

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
PICTURES: Final = Pictures(
    most=contest_home.PUBLIC_MOST,
    endings=sorted(ending.removeprefix(".") for ending in IMAGE_TYPES),
)
"""What a picture a statement shows may be, for an organiser's page to
check before it saves one: a public file served as a picture, no larger
than a page is served."""
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

InputName = Annotated[str, Path(max_length=255, description="The input's name")]
Group = Annotated[str, Path(max_length=255, description="The run entry's `of`: a group or `all`")]
Place = Annotated[
    int, Path(ge=1, le=NUMBER_MAX, description="The run's place under that entry, from 1")
]


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
    inputs a contestant gives, when it falls due and closes for the
    caller, and the runs and settings its `show` shows now.
    """
    return await contest_home.task(session, tasks.task_id_of(scope))


@router.get(
    f"{TASK}/inputs/{{name}}",
    operation_id="listTaskShownInputFiles",
    summary="The files of a setting the task shows",
    response_model=ShownInputFiles,
)
async def list_task_shown_input_files(
    session: OptionalSession, scope: TaskAtPath, name: InputName
) -> ShownInputFiles:
    """A setting the task's `show` lists under `inputs` now that is a file or
    a folder, read with exactly the rights the statement is read with: the
    file, or each file in the folder, by its address at the download door.
    A setting not shown now, one given as a number or text, or one that is
    not there is `not_found`.
    """
    task = tasks.task_id_of(scope)
    found = await (
        contest_home.shown_input(session, task, name)
        if session is not None
        else landing.shown_input(task, name)
    )
    return shown_files(found, f"{task_downloads(scope)}/{INPUTS}/{quote(name, safe='')}")


@router.get(
    f"{TASK}/runs/{{group}}/{{place}}/inputs/{{name}}",
    operation_id="listTaskRunInputFiles",
    summary="The files of a run's input the task shows",
    response_model=ShownInputFiles,
)
async def list_task_run_input_files(
    session: OptionalSession, scope: TaskAtPath, group: Group, place: Place, name: InputName
) -> ShownInputFiles:
    """A run's own input that is a file or a folder, which a run entry of
    the task's `show` names at a moment that has come, the run named by the
    entry's `of` and its place there as the task's page lists it, read with
    exactly the rights the statement is read with: the file, or each file
    in the folder, by its address at the download door. A run or an input
    not shown now is `not_found`, the same as one that is not there.
    """
    task = tasks.task_id_of(scope)
    found = await (
        contest_home.shown_input(session, task, name, group, place)
        if session is not None
        else landing.shown_input(task, name, group, place)
    )
    at = f"{task_downloads(scope)}/{RUNS}/{quote(group, safe='')}/{place}"
    return shown_files(found, f"{at}/{INPUTS}/{quote(name, safe='')}")


def shown_files(found: ShownInput, at: str) -> ShownInputFiles:
    """A shown input's files, by their addresses below `at`, the input's own
    address at the download door: a file at `at` itself, and each file of a
    folder at its path below it, each segment quoted.
    """
    if found.door is not None:
        return ShownInputFiles(files=[ShownFile(path=None, download=at)])
    return ShownInputFiles(
        files=[
            ShownFile(
                path=path,
                download=f"{at}/{quoted(path)}",
            )
            for path in found.files
        ]
    )


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
    """`path` is the file's path under `public/`, served with the statement:
    read with exactly the rights the statement is read with, as the task's
    latest publication holds it, and, for a signed-in caller holding a role
    reaching the task, whether or not it is released, as the task's head
    holds it, the draft the statement's preview draws. Each answer carries
    an `ETag` of its bytes and is asked again each time; `If-None-Match`
    with that tag is answered 304 while the bytes are the same. A path with
    an empty, `.` or `..` segment, or a file that is not there, is
    `not_found`, the same as a task the caller may not read; one larger
    than a page is served is `public_file_too_large`, with the `limit` in
    bytes.
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
