"""What the routes that need no session answer with: the public contests and
the statements of their released tasks, and nothing a contestant's own view
holds.
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel

from unicon.schemas.contest_home import ContestNames, TaskRun


class PublicTask(BaseModel):
    """A released task of a public contest: its name, the label the contest
    gives it, and its title.
    """

    name: str
    label: str
    title: str


class PublicContest(BaseModel):
    """A public contest `where` it is, by the names of its org and itself,
    with its title as `name`, what it says of itself and when it runs.
    `tasks` are its released tasks, and empty in the list of contests.
    """

    where: ContestNames
    name: str
    description: str
    start: datetime
    end: datetime
    tasks: list[PublicTask]


class PublicStatement(BaseModel):
    """A released task of a public contest with its statement in Markdown,
    and the runs and settings its `show` shows now, as a task's page has
    them.
    """

    task: PublicTask
    statement: str
    runs: list[TaskRun] = []
    shown_inputs: dict[str, Any] = {}
