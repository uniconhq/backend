"""What the routes that need no session answer with: the public contests and
the statements of their released tasks, and nothing a contestant's own view
holds.
"""

from datetime import datetime

from forge.api.landing import PublicContest as PublicContestRecord
from forge.api.landing import PublicStatement as PublicStatementRecord
from forge.api.landing import PublicTask as PublicTaskRecord
from forge.api.types import scope_of_place
from pydantic import BaseModel


class PublicTask(BaseModel):
    """A released task of a public contest: its name, the label the contest
    gives it, and its title.
    """

    name: str
    label: str
    title: str

    @classmethod
    def of(cls, task: PublicTaskRecord) -> PublicTask:
        return cls(name=task.name, label=task.label, title=task.title)


class PublicContest(BaseModel):
    """A public contest by its org and name, with its title, what it says of
    itself and when it runs. `tasks` are its released tasks, and empty in the
    list of contests.
    """

    org: str
    name: str
    title: str
    description: str
    start: datetime
    end: datetime
    tasks: list[PublicTask]

    @classmethod
    def of(cls, contest: PublicContestRecord) -> PublicContest:
        scope = scope_of_place(contest.contest)
        return cls(
            org=scope.org,
            name=str(scope.contest),
            title=contest.name,
            description=contest.description,
            start=contest.start,
            end=contest.end,
            tasks=[PublicTask.of(task) for task in contest.tasks],
        )


class PublicStatement(BaseModel):
    """A released task of a public contest with its statement in Markdown."""

    task: PublicTask
    statement: str

    @classmethod
    def of(cls, found: PublicStatementRecord) -> PublicStatement:
        return cls(task=PublicTask.of(found.task), statement=found.statement)
