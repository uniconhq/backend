"""Announcements: an organiser's messages to a contest or a task, and the open
ones a signed-in person reads.

The organiser's four routes, listing every announcement, closed ones
included, posting, editing and closing, are served under the contest and
the task prefixes, made by `router_at`, so each kind gets its own operation
names. Listing needs the observer role at the place and the rest the
manager role. There is no delete: a closed announcement stays readable.

A signed-in person reads the open announcements of a contest they see with
those of each task released to them, beside the contest's home, and of one
released task, beside its page. Those need a session and no role; a contest
or task the caller may not see is not found, the same as one that is not
there.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, status
from forge.api import announcements, contests, tasks
from forge.api.access import Organiser
from forge.api.types import Role, ScopeKind

from unicon.api.deps import CurrentSession
from unicon.api.guard import PREFIX, ContestAtPath, TaskAtPath, require
from unicon.schemas.threads import AnnouncementRequest

CONTEST = PREFIX[ScopeKind.CONTEST]
TASK = PREFIX[ScopeKind.TASK]
Announcement = announcements.Announcement

reading = APIRouter(tags=["announcements"])


@reading.get(
    f"{CONTEST}/home/announcements",
    operation_id="listContestAnnouncements",
    summary="The open announcements of a contest and its released tasks",
    response_model=list[Announcement],
)
async def list_contest_announcements(
    session: CurrentSession, scope: ContestAtPath
) -> tuple[Announcement, ...]:
    """The contest's own first, then each released task's in the contest's
    order, each oldest first.
    """
    return await announcements.contest(session, contests.contest_id_of(scope))


@reading.get(
    f"{TASK}/page/announcements",
    operation_id="listTaskAnnouncements",
    summary="The open announcements of a released task",
    response_model=list[Announcement],
)
async def list_task_announcements(
    session: CurrentSession, scope: TaskAtPath
) -> tuple[Announcement, ...]:
    """Oldest first."""
    return await announcements.task(session, tasks.task_id_of(scope))


def router_at(kind: ScopeKind) -> APIRouter:
    """The organiser's announcement routes under the prefix of `kind`, a
    contest or a task.
    """
    name = kind.value.capitalize()
    router = APIRouter(prefix=PREFIX[kind], tags=["announcements"])
    Observer = Annotated[Organiser, Depends(require(Role.OBSERVER, kind))]
    Manager = Annotated[Organiser, Depends(require(Role.MANAGER, kind))]

    @router.get(
        "/announcements",
        operation_id=f"manage{name}Announcements",
        summary="Every announcement here, closed ones included",
        response_model=list[Announcement],
    )
    async def manage(organiser: Observer) -> tuple[Announcement, ...]:
        """Oldest first, each saying whether it is closed and, when it answers
        a question, which.
        """
        return await announcements.manage(organiser, organiser.scope)

    @router.post(
        "/announcements",
        operation_id=f"post{name}Announcement",
        summary="Post an announcement",
        status_code=status.HTTP_201_CREATED,
        response_model=Announcement,
    )
    async def post(organiser: Manager, body: AnnouncementRequest) -> Announcement:
        """Posted as the caller. An empty or too long title or text is
        `invalid_message`, naming which.
        """
        return await announcements.post(
            organiser, organiser.scope, title=body.title, body=body.body
        )

    @router.patch(
        "/announcements/{number}",
        operation_id=f"edit{name}Announcement",
        summary="Change an announcement's title and text",
        response_model=Announcement,
    )
    async def edit(organiser: Manager, number: int, body: AnnouncementRequest) -> Announcement:
        """Changed as the caller, keeping what it answers."""
        return await announcements.edit(
            organiser, organiser.scope, number, title=body.title, body=body.body
        )

    @router.post(
        "/announcements/{number}/close",
        operation_id=f"close{name}Announcement",
        summary="Close an announcement, which stays readable",
        response_model=Announcement,
    )
    async def close(organiser: Manager, number: int) -> Announcement:
        """Closing a closed one changes nothing."""
        return await announcements.close(organiser, organiser.scope, number)

    return router
