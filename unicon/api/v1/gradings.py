"""An organiser's view of and controls over a task's gradings: the list of
them, newest first, each with who submitted it, where it stands, why it
failed and whether it is its submission's latest attempt, and a grading's
run log, which need the observer role at the task; and, with the manager
role there, cancelling the latest attempt of a submission that reads as a
system error, with a sentence its contestant reads, when a regrade would
only repeat the fault; retrying a submission's latest attempt once it is
finished as a new attempt against the publication it graded against, a
stuck one included, whose old run is cancelled; having a submission whose
latest attempt is a system error, or staff cancelled, count as its last
good result, and taking that back; and rejudging every submission's latest
attempt against the task's current publication.

An observer of the task also reads any contestant's or team's submission
as its row reads it with everything filled in, beside its grading
(TASK-FORMAT.md section 1.7): the row picked by `user_id` or `team`, as the
boards pick one, and the submission by its number among the row's.

Anyone holding a role at a contest or at any of its tasks reads the
gradings of the tasks they observe as one feed, newest first, each with
its task's name and letter and who submitted it, narrowed by task, by a
contestant's username, by team and by status; and how many of them wait
for a machine, `queued` and `dispatched`, counted when asked. Forge
narrows both to the tasks the caller observes.

A grading is named by its id under its task's prefix, which is where the
guard reads the scope the role is checked at, as for every other organiser
route. A grading of any other task is no such grading here, whatever roles
the caller holds there, so a path names one grading of one task or nothing.
Forge checks the role again at the grading's own task.

A log is plain text that the browser is told not to guess the type of and
that runs nothing, so a log is never rendered as a page of the platform's.
"""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Response
from forge.api import contests, gradings, names, submissions, tasks
from forge.api.access import Organiser
from forge.api.boards import TeamOwner, UserOwner
from forge.api.errors import NotFound, Rejected
from forge.api.gradings import GradingStatus
from forge.api.types import Role, ScopeKind, TaskId

from unicon.api.guard import PREFIX, anywhere, require
from unicon.api.v1.submissions import Number
from unicon.schemas.gradings import (
    USERNAME_MAX,
    USERNAME_PATTERN,
    CancelRequest,
    FeedEntry,
    Grading,
    Rejudged,
)
from unicon.schemas.submissions import OrganisedSubmission

CONTEST = PREFIX[ScopeKind.CONTEST]
TASK = PREFIX[ScopeKind.TASK]

router = APIRouter(prefix=TASK, tags=["gradings"])
feed = APIRouter(prefix=CONTEST, tags=["gradings"])

InContest = Annotated[Organiser, Depends(anywhere(ScopeKind.CONTEST))]
TaskManager = Annotated[Organiser, Depends(require(Role.MANAGER, ScopeKind.TASK))]
TaskObserver = Annotated[Organiser, Depends(require(Role.OBSERVER, ScopeKind.TASK))]
NO_SUCH_GRADING = "There is no such grading."
LIST_MOST = 500
LOG = "text/plain; charset=utf-8"
LOG_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Content-Security-Policy": "default-src 'none'; sandbox",
    "Cache-Control": "private, no-store",
}


@router.get(
    "/gradings",
    operation_id="listGradings",
    summary="The task's gradings, newest first",
    response_model=list[FeedEntry],
)
async def list_gradings(
    organiser: TaskObserver, limit: Annotated[int, Query(ge=1, le=LIST_MOST)] = 100
) -> list[dict[str, Any]]:
    """At most `limit` of the task's gradings, newest first, each as the feed
    gives it, with who submitted it. One whose run did not begin, did not
    report by its deadline, or was lost by the CI reads as `system_error`
    with the reason in `error`, whatever its row still says.
    """
    rows = await gradings.list(organiser, tasks.task_id_of(organiser.scope), limit=limit)
    return [_entry(row) for row in rows]


@router.get(
    "/organise/submissions/{number}",
    operation_id="getOrganisedSubmission",
    summary="A row's submission scored, with everything its row is not shown yet",
    response_model=OrganisedSubmission,
)
async def get_organised_submission(
    organiser: TaskObserver,
    number: Number,
    user_id: Annotated[int | None, Query(description="The contestant whose row it is")] = None,
    team: Annotated[uuid.UUID | None, Query(description="The team whose row it is")] = None,
) -> submissions.Submission:
    """The row is a contestant or a team, one of the two, or `rejected`. A
    row with no submission of that number is `not_found`.
    """
    row: UserOwner | TeamOwner
    if user_id is not None and team is None:
        row = UserOwner(user_id)
    elif team is not None and user_id is None:
        row = TeamOwner(team)
    else:
        raise Rejected("Pick a contestant or a team, one of the two.")
    return await submissions.organised(organiser, tasks.task_id_of(organiser.scope), row, number)


@router.get(
    "/gradings/{grading}/log",
    operation_id="readGradingLog",
    summary="The run log of one of the task's gradings",
    response_class=Response,
    responses={
        200: {
            "description": "The log, as the run wrote it.",
            "content": {LOG: {"schema": {"type": "string"}}},
        }
    },
)
async def read_grading_log(organiser: TaskObserver, grading: uuid.UUID) -> Response:
    """The log of the grading's run. A grading with no log is `not_found`,
    the same as one that is not there, and a log larger than the platform
    reads back is `log_too_large` with the `limit` in bytes.
    """
    content = await gradings.run_log(organiser, await _of_this_task(organiser, grading))
    return Response(content=content, media_type=LOG, headers=LOG_HEADERS)


@router.post(
    "/gradings/{grading}/cancel",
    operation_id="cancelGrading",
    summary="End a submission whose grading is a system error, saying why",
    response_model=Grading,
)
async def cancel_grading(
    organiser: TaskManager, grading: uuid.UUID, body: CancelRequest
) -> gradings.GradingRecord:
    """The grading as it now stands, `cancelled` with `cancel_reason`, the
    sentence its contestant reads; one that reads as a system error because
    its run is overdue or lost keeps that as its `error`. A sentence that is
    empty or over 500 characters is `invalid_reason`, a grading that is not
    a system error `wrong_status` with its status as `current`, and an
    earlier attempt of a submission graded again `conflict`, since the
    latest is the one to cancel.
    """
    return await gradings.cancel(organiser, await _of_this_task(organiser, grading), body.reason)


@router.post(
    "/gradings/{grading}/retry",
    operation_id="retryGrading",
    summary="Grade a finished grading again as a new attempt",
    response_model=Grading,
)
async def retry_grading(organiser: TaskManager, grading: uuid.UUID) -> gradings.GradingRecord:
    """The new attempt, queued. The old one is kept as it was, unless it reads
    as a system error only because its run is overdue or lost: then it is
    ended with that reason, and its run cancelled at the CI. One that is not
    finished is `wrong_status` with its status as `current`, and so is a
    submission staff cancelled, which that ended, as `cancelled`; an earlier
    attempt of a submission graded again is `conflict`, since the latest is
    the one to retry, and so is one while another attempt of it is being
    graded.
    """
    return await gradings.retry(organiser, await _of_this_task(organiser, grading))


@router.put(
    "/gradings/{grading}/fallback",
    operation_id="fallBackGrading",
    summary="Count a broken grading's submission as its last good result",
    response_model=Grading,
)
async def fall_back_grading(organiser: TaskManager, grading: uuid.UUID) -> gradings.GradingRecord:
    """The grading as it now stands, its `fallback` `staff`: its submission
    counts as `last_good`, the latest earlier attempt that finished with a
    result, whatever the contest's `on_system_error` says, on the boards,
    to its contestant and under the task's limit. Asked again, it changes
    nothing. A grading that is neither a system error nor staff cancelled is
    `wrong_status` with its status as `current`; an earlier attempt of a
    submission graded again, and a submission with no earlier result, are
    `conflict`.
    """
    return await gradings.fall_back(organiser, await _of_this_task(organiser, grading))


@router.delete(
    "/gradings/{grading}/fallback",
    operation_id="clearGradingFallback",
    summary="Take back staff's fallback on a grading",
    response_model=Grading,
)
async def clear_grading_fallback(
    organiser: TaskManager, grading: uuid.UUID
) -> gradings.GradingRecord:
    """The grading as it now stands, its submission counting as the contest's
    `on_system_error` says. A grading with no fallback of staff's changes
    nothing.
    """
    return await gradings.clear_fallback(organiser, await _of_this_task(organiser, grading))


@router.post(
    "/rejudge",
    operation_id="rejudgeTask",
    summary="Grade every submission of the task again against its current publication",
    response_model=Rejudged,
)
async def rejudge_task(organiser: TaskManager) -> gradings.Rejudged:
    """How many new attempts it queued, and how many earlier attempts it
    cancelled first and left to finish. A task with no publication is
    `not_found`.
    """
    return await gradings.rejudge(organiser, tasks.task_id_of(organiser.scope))


@feed.get(
    "/gradings",
    operation_id="listContestGradings",
    summary="The contest's gradings as one feed, newest first",
    response_model=list[FeedEntry],
)
async def list_contest_gradings(
    organiser: InContest,
    org: str,
    contest: str,
    task: Annotated[str | None, Query(description="One task, by name")] = None,
    user: Annotated[
        str | None,
        Query(
            description="One contestant's submissions, their own and their teams', by username",
            pattern=USERNAME_PATTERN,
            max_length=USERNAME_MAX,
        ),
    ] = None,
    team: Annotated[uuid.UUID | None, Query(description="One team's submissions")] = None,
    status: Annotated[GradingStatus | None, Query(description="As the grading reads")] = None,
    limit: Annotated[int, Query(ge=1, le=LIST_MOST)] = 100,
) -> list[dict[str, Any]]:
    """At most `limit` gradings of the contest's tasks the caller observes,
    newest first, every attempt a row of its own, so a submission graded
    again shows more than once. One whose run is overdue or lost reads as
    `system_error` with the reason, and a filter by status takes it as it
    reads. A task, username or team the contest does not have, or a task
    the caller does not observe, gives no rows; a username that breaks the
    forge's rule for one is a `validation_error`.
    """
    task_id: TaskId | None = None
    if task is not None:
        try:
            task_id = tasks.task_id_of(await names.scope_at(org, contest, task))
        except NotFound:
            return []
    rows = await gradings.feed(
        organiser,
        contests.contest_id_of(organiser.scope),
        task=task_id,
        user=user,
        team=team,
        status=status,
        limit=limit,
    )
    return [_entry(row) for row in rows]


@feed.get(
    "/gradings/queue",
    operation_id="getContestQueueDepth",
    summary="How many of the contest's gradings wait for a machine",
)
async def get_contest_queue_depth(organiser: InContest) -> gradings.QueueDepth:
    """`queued`, whose run is not started yet, and `dispatched`, whose run
    the CI holds until a machine takes it, counted when asked over the
    contest's tasks the caller observes. One that is overdue or lost reads
    as a system error and is not counted.
    """
    return await gradings.queue_depth(organiser, contests.contest_id_of(organiser.scope))


def _entry(row: gradings.FeedEntry) -> dict[str, Any]:
    return {"grading": row.grading, "task": row.task_name, "label": row.label, "by": row.by}


async def _of_this_task(organiser: Organiser, grading: uuid.UUID) -> uuid.UUID:
    """The grading, when it is one of the task the path names. `not_found`
    for one of another task, the same as for none at all.
    """
    if await gradings.task_of(grading) != tasks.task_id_of(organiser.scope):
        raise NotFound(NO_SUCH_GRADING)
    return grading
