"""What the announcement and clarification routes take: an announcement's
title and text, a question with the task it may name, and a comment. What
they answer with are the forge's own `Announcement` and `Clarification`,
every field of which may go out to the caller the route admits.
"""

from pydantic import BaseModel


class AnnouncementRequest(BaseModel):
    """An announcement's title and text, as posted or as edited."""

    title: str
    body: str


class QuestionRequest(BaseModel):
    """A question's title and text, and the name of the task it is about,
    when it is about one released to the asker.
    """

    title: str
    body: str
    task: str | None = None


class CommentRequest(BaseModel):
    """One message under a question: a contestant's follow-up or an
    organiser's reply.
    """

    body: str
