from datetime import datetime
from functools import cached_property
from logging import getLogger
from typing import Annotated, Any

from pydantic import BaseModel, Field
from sqlmodel._compat import SQLModelConfig

from unicon_backend.evaluator.tasks.multiple_choice import MultipleChoiceTask, MultipleResponseTask
from unicon_backend.evaluator.tasks.programming.base import ProgrammingTask
from unicon_backend.evaluator.tasks.short_answer import ShortAnswerTask
from unicon_backend.lib.common import CustomSQLModel
from unicon_backend.models.file import FileORM

logger = getLogger(__name__)


class UserInput(BaseModel):
    task_id: int
    value: Any


Task = Annotated[
    ProgrammingTask | MultipleChoiceTask | MultipleResponseTask | ShortAnswerTask,
    Field(discriminator="type"),
]


class Problem(CustomSQLModel):
    model_config = SQLModelConfig(from_attributes=True)

    id: int | None = None
    name: str
    restricted: bool
    published: bool = Field(default=False)
    leaderboard_enabled: bool = Field(default=False)
    description: str
    supporting_files: list[FileORM] = Field(default_factory=list)
    tasks: list[Task]
    started_at: datetime
    ended_at: datetime | None = Field(default=None)
    closed_at: datetime | None = Field(default=None)

    @cached_property
    def task_index(self) -> dict[int, Task]:
        return {task.id: task for task in self.tasks}

    def redact_private_fields(self):
        """This is a destructive in-place action. Do not attempt to assemble code after redacting private fields."""
        for task in self.tasks:
            task.redact_private_fields()
