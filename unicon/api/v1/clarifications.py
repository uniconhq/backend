"""Clarifications: a contestant's private questions and the organisers'
answers.

A contestant asks, lists their own questions and follows one up, under the
contest's prefix; that needs a session and no role, and forge refuses
anyone who is not an approved contestant of the contest with
`not_approved`. A follow-up on an answered question opens it again.

An organiser has the inbox, every question still open across the org, for
anyone holding a role anywhere in it (`forbidden` otherwise); every question
of one contest, answered ones included, which needs the observer role
there; and, with the manager role at the contest, a reply, which leaves the
question open, marking it answered, which closes it with or without a
reply, taking the mark off again, and an answer made public as an
announcement pointing at the question. A question is named by its asker's
user id and its number among their questions in the contest.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, status
from forge.api import announcements, clarifications, contests
from forge.api.access import Organiser
from forge.api.types import Role, ScopeKind

from unicon.api.deps import CurrentSession
from unicon.api.guard import PREFIX, ContestAtPath, require
from unicon.schemas.threads import AnnouncementRequest, CommentRequest, QuestionRequest

ORG = PREFIX[ScopeKind.ORG]
CONTEST = PREFIX[ScopeKind.CONTEST]
QUESTION = f"{CONTEST}/clarifications/{{asker}}/{{number}}"
Clarification = clarifications.Clarification

router = APIRouter(tags=["clarifications"])

ContestObserver = Annotated[Organiser, Depends(require(Role.OBSERVER, ScopeKind.CONTEST))]
ContestManager = Annotated[Organiser, Depends(require(Role.MANAGER, ScopeKind.CONTEST))]


@router.post(
    f"{CONTEST}/questions",
    operation_id="askQuestion",
    summary="Ask the organisers a question, privately",
    status_code=status.HTTP_201_CREATED,
    response_model=Clarification,
)
async def ask_question(
    session: CurrentSession, scope: ContestAtPath, body: QuestionRequest
) -> Clarification:
    """Asked as the caller. A task that is not released to them is
    `not_found`, and an empty or too long title or text `invalid_message`.
    """
    return await clarifications.ask(
        session, contests.contest_id_of(scope), title=body.title, body=body.body, task=body.task
    )


@router.get(
    f"{CONTEST}/questions",
    operation_id="listMyQuestions",
    summary="The caller's own questions in the contest",
    response_model=list[Clarification],
)
async def list_my_questions(
    session: CurrentSession, scope: ContestAtPath
) -> tuple[Clarification, ...]:
    """Oldest first, each with every message under it."""
    return await clarifications.mine(session, contests.contest_id_of(scope))


@router.post(
    f"{CONTEST}/questions/{{number}}/comments",
    operation_id="followUpQuestion",
    summary="Comment again on one's own question",
    response_model=Clarification,
)
async def follow_up_question(
    session: CurrentSession, scope: ContestAtPath, number: int, body: CommentRequest
) -> Clarification:
    """On an answered question this takes the mark off and opens it."""
    return await clarifications.follow_up(
        session, contests.contest_id_of(scope), number, body=body.body
    )


@router.get(
    f"{ORG}/clarifications",
    operation_id="listClarificationInbox",
    summary="Every question still open across the org",
    response_model=list[Clarification],
)
async def list_clarification_inbox(session: CurrentSession, org: str) -> tuple[Clarification, ...]:
    """Oldest first, each only where the caller observes its contest."""
    return await clarifications.inbox(session, org)


@router.get(
    f"{CONTEST}/clarifications",
    operation_id="listContestClarifications",
    summary="Every question of the contest, answered ones included",
    response_model=list[Clarification],
)
async def list_contest_clarifications(organiser: ContestObserver) -> tuple[Clarification, ...]:
    """Oldest first."""
    return await clarifications.of_contest(organiser, contests.contest_id_of(organiser.scope))


@router.post(
    f"{QUESTION}/replies",
    operation_id="replyToQuestion",
    summary="Reply to a question, leaving it open",
    response_model=Clarification,
)
async def reply_to_question(
    organiser: ContestManager, asker: int, number: int, body: CommentRequest
) -> Clarification:
    """Posted as the caller."""
    return await clarifications.reply(
        organiser, contests.contest_id_of(organiser.scope), asker, number, body=body.body
    )


@router.put(
    f"{QUESTION}/answered",
    operation_id="markQuestionAnswered",
    summary="Mark a question answered, closing it",
    response_model=Clarification,
)
async def mark_question_answered(
    organiser: ContestManager, asker: int, number: int
) -> Clarification:
    """With or without a reply first; marking a marked one changes nothing."""
    return await clarifications.mark(
        organiser, contests.contest_id_of(organiser.scope), asker, number
    )


@router.delete(
    f"{QUESTION}/answered",
    operation_id="unmarkQuestionAnswered",
    summary="Take the answered mark off a question, opening it again",
    response_model=Clarification,
)
async def unmark_question_answered(
    organiser: ContestManager, asker: int, number: int
) -> Clarification:
    """Unmarking one that is not marked changes nothing."""
    return await clarifications.unmark(
        organiser, contests.contest_id_of(organiser.scope), asker, number
    )


@router.post(
    f"{QUESTION}/announcement",
    operation_id="answerQuestionPublicly",
    summary="Turn an answer into an announcement every contestant reads",
    status_code=status.HTTP_201_CREATED,
    response_model=announcements.Announcement,
)
async def answer_question_publicly(
    organiser: ContestManager, asker: int, number: int, body: AnnouncementRequest
) -> announcements.Announcement:
    """On the task the question names, or else on the contest, pointing at
    the question, which stays private.
    """
    return await clarifications.answer_publicly(
        organiser,
        contests.contest_id_of(organiser.scope),
        asker,
        number,
        title=body.title,
        body=body.body,
    )
