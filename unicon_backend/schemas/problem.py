from datetime import datetime

from pydantic import BaseModel, ConfigDict

from unicon_backend.evaluator.problem import Problem, Task


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
    description: str
    task_order: list[TaskOrder]
    started_at: datetime
    ended_at: datetime | None
    closed_at: datetime | None


class TaskUpdate(BaseModel):
    task: Task
    rerun: bool


class ParseRequest(BaseModel):
    content: str
