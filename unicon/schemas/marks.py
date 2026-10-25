"""What the marks routes answer with."""

from datetime import datetime

from pydantic import BaseModel


class Marks(BaseModel):
    """The marks the caller's row holds on a task, for a leaderboard reading which
    of its submissions an entrant marks: the numbers of the submissions
    marked, the most it may hold, and the row's close on the task, after
    which they are frozen.
    """

    numbers: list[int]
    most: int
    closes_at: datetime
    frozen: bool
