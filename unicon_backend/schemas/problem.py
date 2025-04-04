from datetime import datetime

from pydantic import BaseModel, ConfigDict

from unicon_backend.evaluator.problem import Problem, Task
from unicon_backend.evaluator.tasks.programming.base import ProgrammingTask


class MiniProblemPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str


class ProblemPublic(Problem):
    # permissions

    edit: bool
    make_submission: bool
    make_submission_without_limit: bool
    view_hidden_details: bool


class TaskOrder(BaseModel):
    id: int
    order_index: int


class ProblemUpdate(BaseModel):
    name: str
    restricted: bool
    published: bool
    leaderboard_enabled: bool
    description: str
    task_order: list[TaskOrder]
    started_at: datetime
    ended_at: datetime | None
    closed_at: datetime | None


class LeaderboardUserTaskResult(BaseModel):
    task_id: int
    score: int
    attempts: int
    passed: bool
    latest_attempt_date: datetime | None = None


class LeaderboardUser(BaseModel):
    id: int
    username: str
    task_results: list[LeaderboardUserTaskResult]
    solved: int


class Leaderboard(BaseModel):
    tasks: list[ProgrammingTask]
    results: list[LeaderboardUser]


class TaskUpdate(BaseModel):
    task: Task
    rerun: bool


class ParseRequest(BaseModel):
    content: str
