"""An organiser's view of and controls over a task's gradings: the list of
them, newest first, each with who submitted it, where it stands, why it
failed and whether it is its submission's latest attempt, and a grading's
run log, which need the observer role at the task; and, with the manager
role there, cancelling the latest attempt of a submission that reads as a
system error, with a sentence its contestant reads, when a regrade would
only repeat the fault; retrying a submission's latest attempt once it is
finished as a new attempt against the publication it graded against, a
stuck one included, whose old run is cancelled, as often as staff like
after the one retry the platform makes by itself of a grading that fails;
and rejudging every submission's latest attempt against the task's current
publication. A failed or cancelled attempt never takes a result away: a
submission counts its latest attempt that finished with a result. A delayed
submission is graded again, by a retry or a rejudge, only while its entrant
has room under the task's most submissions, and otherwise ends
`over_limit`; a grading's `retry_limit` says beforehand when a retry would.

A rejudge, and the regrade a save that changes how the task grades starts,
is kept as one regrade of many: anyone holding a role in the contest reads
each task's latest one they observe summed up by what it did to each
submission against the result it replaced, and the feed narrowed to its
gradings, each with that change; a manager of the task dismisses it from
the contest's page, and reads a run task's regrade by each value and
verdict it changed, old to new, with each leaderboard that reads the task
before and after for a manager or admin of the contest alone.

An observer of the task also reads any entrant's submission as its row
reads it with everything filled in, beside its grading (TASK-FORMAT.md
section 1.7): the row picked by `entrant`, as the leaderboards pick one, and the
submission by its number among the row's; and a text a run task's result
names, one at a time. A manager of the task enters a mark for one of a
submission's values that reads an `entered` block; every mark is kept, the
latest counts, and a regrade never touches one. Organisers read the value
with the rest of the submission's values at once; its entrant reads it
only once a leaderboard's cell shown to them counted the submission, or, when
no cell did, from the task's reveal, as forge decides.

An observer of the task reads its grading queue (#505), and enters
nothing from it: each row the task has closed for, its extension
included, by name, with the submissions to the task that a cell of any of
the contest's leaderboards counted, as staff read them, each with the
leaderboards and columns that counted it and the mark of each `entered`
value, or null while missing; an observer with a role at the task alone,
none at its contest, is listed only the cells that read this task alone.
Forge works it out from what the cells counted on each read.

Anyone holding a role at a contest or at any of its tasks reads the
gradings of the tasks they observe as one feed, newest first, each with
its task's name and letter, its entrant and the member who submitted it,
narrowed by task, by that member's username, by entrant, by status and to
each submission's latest attempt; and how many of them wait for a machine,
`queued` and `dispatched`, and for staff, `failed`, counted when asked, so
a contest's page can say how many gradings failed and link to the feed
filtered to them (`status=system_error&latest=true`). Forge narrows both
to the tasks the caller observes.

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
from forge.api import contests, entries, gradings, names, regrades, submissions, tasks
from forge.api.access import Organiser
from forge.api.errors import NotFound
from forge.api.gradings import GradingStatus
from forge.api.leaderboards import EntrantOwner
from forge.api.regrades import ChangeKind
from forge.api.types import Role, ScopeKind, TaskId

from unicon.api.guard import PREFIX, anywhere, require
from unicon.api.v1.submissions import (
    TEXT,
    TEXT_HEADERS,
    TEXT_RESPONSES,
    Number,
    Output,
    TextName,
)
from unicon.schemas.gradings import (
    USERNAME_MAX,
    USERNAME_PATTERN,
    CancelRequest,
    EnteredMark,
    EnterMarkRequest,
    FeedEntry,
    Grading,
    QueueRow,
    RegradeSummary,
    Rejudged,
    RunRegradeSummary,
)
from unicon.schemas.leaderboards import counted_of, header_of, sort_of
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
    rows = await gradings.list_gradings(organiser, tasks.task_id_of(organiser.scope), limit=limit)
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
    entrant: Annotated[uuid.UUID, Query(description="The entrant whose row it is")],
) -> submissions.Submission:
    """A row with no submission of that number is `not_found`."""
    row = EntrantOwner(entrant)
    return await submissions.organised(organiser, tasks.task_id_of(organiser.scope), row, number)


@router.get(
    "/organise/submissions/{number}/texts/{output}/{name}",
    operation_id="readOrganisedSubmissionText",
    summary="A text a row's submission names, as organisers read it",
    response_class=Response,
    responses=TEXT_RESPONSES,
)
async def read_organised_submission_text(
    organiser: TaskObserver,
    number: Number,
    output: Output,
    name: TextName,
    entrant: Annotated[uuid.UUID, Query(description="The entrant whose row it is")],
) -> Response:
    """A text the submission's result names, as `output` and `name`, read
    as organisers read the submission. Any other is `not_found`.
    """
    found = await submissions.read_organised_text(
        organiser, tasks.task_id_of(organiser.scope), EntrantOwner(entrant), number, output, name
    )
    return Response(content=found, media_type=TEXT, headers=TEXT_HEADERS)


@router.post(
    "/organise/submissions/{number}/entries",
    operation_id="enterMark",
    summary="Enter a mark for one of a row's submission's entered values",
    response_model=EnteredMark,
)
async def enter_mark(
    organiser: TaskManager,
    number: Number,
    body: EnterMarkRequest,
    entrant: Annotated[uuid.UUID, Query(description="The entrant whose row it is")],
) -> entries.Entered:
    """The mark as it was kept. A value the task's live version gives no
    `entered` block, or a mark that is not a plain number within its
    bounds, is `invalid_mark`; a row with no submission of that number is
    `not_found`.
    """
    return await entries.enter(
        organiser,
        tasks.task_id_of(organiser.scope),
        EntrantOwner(entrant),
        number,
        body.value,
        body.mark,
    )


@router.get(
    "/organise/queue",
    operation_id="readGradingQueue",
    summary="The task's grading queue: each closed row's submissions its cells counted",
    response_model=list[QueueRow],
)
async def read_grading_queue(organiser: TaskObserver) -> list[dict[str, Any]]:
    """Each row the task has closed for, its extension included, by name,
    with the submissions to the task a cell of any leaderboard counted,
    each with the cells that counted it and the mark of each `entered`
    value, null while missing; a caller with a role at the task alone is
    listed only the cells that read this task alone. A row with nothing
    counted is left out. A task that does not grade by runs is
    `not_a_run_task`, and one never published `not_found`.
    """
    rows = await entries.queue(organiser, tasks.task_id_of(organiser.scope))
    return [
        {
            "row": {"entrant": row.owner.entrant_id, "name": row.name},
            "closed_at": row.closed_at,
            "submissions": [
                {
                    "number": each.number,
                    "counted_by": [
                        {"leaderboard": leaderboard, "column": column}
                        for leaderboard, column in each.counted_by
                    ],
                    "marks": [{"value": value, "mark": mark} for value, mark in each.marks],
                }
                for each in row.submissions
            ],
        }
        for row in rows
    ]


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
            description="The submissions one member made, by username",
            pattern=USERNAME_PATTERN,
            max_length=USERNAME_MAX,
        ),
    ] = None,
    entrant: Annotated[uuid.UUID | None, Query(description="One entrant's submissions")] = None,
    status: Annotated[GradingStatus | None, Query(description="As the grading reads")] = None,
    latest: Annotated[bool, Query(description="Only each submission's latest attempt")] = False,
    regrade: Annotated[
        uuid.UUID | None, Query(description="One regrade of many's gradings, each with its change")
    ] = None,
    change: Annotated[
        ChangeKind | None, Query(description="With regrade, what it did to the submission")
    ] = None,
    limit: Annotated[int, Query(ge=1, le=LIST_MOST)] = 100,
) -> list[dict[str, Any]]:
    """At most `limit` gradings of the contest's tasks the caller observes,
    newest first, every attempt a row of its own, so a submission graded
    again shows more than once, or, with `latest`, only each submission's
    latest attempt. One whose run is overdue or lost reads as
    `system_error` with the reason, and a filter by status takes it as it
    reads, so `status=system_error&latest=true` gives the failed gradings
    the queue's `failed` counts. A task, username or entrant the contest does not have, or a task
    the caller does not observe, gives no rows; a username that breaks the
    forge's rule for one is a `validation_error`.

    With `regrade`, the regrade of many a summary of `/gradings/regrades`
    names, it lists that regrade's gradings, one per submission, its latest
    attempt of the regrade, newest first, each with `change`, what it did
    to the submission beside the result it replaced, the earlier and new
    tests accepted side by side; `change` narrows them to one kind, and `user` and
    `entrant` narrow as ever, while `task`, `status` and `latest` are not
    read with it. A regrade the caller cannot see gives no rows, and so
    does `change` without `regrade`.
    """
    contest_id = contests.contest_id_of(organiser.scope)
    if regrade is not None:
        found = await regrades.gradings_of(
            organiser, contest_id, regrade, change=change, user=user, entrant=entrant, limit=limit
        )
        return [_entry(row) for row in found]
    if change is not None:
        return []
    task_id: TaskId | None = None
    if task is not None:
        try:
            task_id = tasks.task_id_of(await names.scope_at(org, contest, task))
        except NotFound:
            return []
    rows = await gradings.feed(
        organiser,
        contest_id,
        task=task_id,
        user=user,
        entrant=entrant,
        status=status,
        latest=latest,
        limit=limit,
    )
    return [_entry(row) for row in rows]


@feed.get(
    "/gradings/queue",
    operation_id="getContestQueueDepth",
    summary="How many of the contest's gradings wait for a machine or for staff",
)
async def get_contest_queue_depth(organiser: InContest) -> gradings.QueueDepth:
    """`queued`, whose run is not started yet, and `dispatched`, whose run
    the CI holds until a machine takes it, counted when asked over the
    contest's tasks the caller observes, one that is overdue or lost
    reading as a system error and not counted there; and `failed`, the
    submissions' latest attempts that read as a system error, which wait
    for their retry or for staff: the gradings the feed gives with
    `status=system_error&latest=true`.
    """
    return await gradings.queue_depth(organiser, contests.contest_id_of(organiser.scope))


@feed.get(
    "/gradings/regrades",
    operation_id="listContestRegrades",
    summary="Each task's latest regrade of many, with what it changed",
    response_model=list[RegradeSummary],
)
async def list_contest_regrades(organiser: InContest) -> list[dict[str, Any]]:
    """The latest regrade of each of the contest's tasks the caller
    observes, newest first, a staff rejudge or the regrade a save that
    changed how the task grades started, summed up by what it did to each
    submission, until a newer regrade of the task replaces it or a manager
    of the task dismisses it. Each summary's `id` reads its gradings on the
    feed, `?regrade=<id>`, narrowed to one kind with `&change=`.
    """
    found = await regrades.latest(organiser, contests.contest_id_of(organiser.scope))
    return [_summary(row) for row in found]


@router.post(
    "/regrades/{regrade}/dismiss",
    operation_id="dismissRegrade",
    summary="Take the task's regrade off the contest's page",
    status_code=204,
)
async def dismiss_regrade(organiser: TaskManager, regrade: uuid.UUID) -> Response:
    """For everyone; one dismissed already stays so. A regrade of another
    task is `not_found`, the same as none.
    """
    await regrades.dismiss(organiser, tasks.task_id_of(organiser.scope), regrade)
    return Response(status_code=204)


@router.get(
    "/regrades/{regrade}",
    operation_id="readRunRegrade",
    summary="What a run task's regrade changed, value by value",
    response_model=RunRegradeSummary,
)
async def read_run_regrade(organiser: TaskManager, regrade: uuid.UUID) -> dict[str, Any]:
    """Each submission whose values or verdicts the regrade changed, old to
    new, worked out on read, a bounded few and the rest counted; how many
    are still running and how many it cannot compare; and, for a manager
    or admin of the contest, each leaderboard that reads the task before and
    after. A regrade of another task is `not_found`, the same as none, and
    so is one of a task graded test by test, whose gradings say what it
    changed.
    """
    found = await regrades.run_summary(organiser, tasks.task_id_of(organiser.scope), regrade)
    return {
        "id": found.id,
        "cause": found.cause,
        "publication": found.publication,
        "total": found.total,
        "running": found.running,
        "failed": found.failed,
        "unread": found.unread,
        "changed": [
            {
                "grading": each.grading,
                "number": each.number,
                "values": each.values,
                "verdicts": each.verdicts,
                "more_verdicts": each.more_verdicts,
            }
            for each in found.changed
        ],
        "more_changed": found.more_changed,
        "leaderboards": None
        if found.leaderboards is None
        else [_diff(leaderboard) for leaderboard in found.leaderboards],
    }


def _diff(leaderboard: regrades.LeaderboardDiff) -> dict[str, Any]:
    return {
        "leaderboard": leaderboard.leaderboard,
        "title": leaderboard.title,
        "headers": [header_of(header) for header in leaderboard.headers],
        "sort": sort_of(leaderboard.sort),
        "rows": [
            {
                "row": {"entrant": row.owner.entrant_id, "name": row.name},
                "place_before": row.place_before,
                "place_after": row.place_after,
                "cells": [
                    {
                        "column": cell.column,
                        "before": cell.before,
                        "after": cell.after,
                        "waiting": counted_of(cell.waiting),
                    }
                    for cell in row.cells
                ],
                "regrading": counted_of(row.regrading),
            }
            for row in leaderboard.rows
        ],
        "unread": leaderboard.unread,
    }


def _entry(row: gradings.FeedEntry) -> dict[str, Any]:
    return {"grading": row.grading, "task": row.task_name, "label": row.label, "by": row.by}


def _summary(row: regrades.Summary) -> dict[str, Any]:
    """A regrade's summary with its task by name, as the feed names one."""
    return {
        "id": row.id,
        "task": row.task_name,
        "label": row.label,
        "cause": row.cause,
        "publication": row.publication,
        "started_at": row.started_at,
        "started_by": row.started_by,
        "started_by_name": row.started_by_name,
        "total": row.total,
        "graded": row.graded,
        "running": row.running,
        "counts": row.counts,
    }


async def _of_this_task(organiser: Organiser, grading: uuid.UUID) -> uuid.UUID:
    """The grading, when it is one of the task the path names. `not_found`
    for one of another task, the same as for none at all.
    """
    if await gradings.task_of(grading) != tasks.task_id_of(organiser.scope):
        raise NotFound(NO_SUCH_GRADING)
    return grading
