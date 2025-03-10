import abc
from enum import Enum
from typing import Any, Generic, TypeVar

from pydantic import BaseModel

TaskUserInput = TypeVar("TaskUserInput")
TaskResult = TypeVar("TaskResult")


class TaskType(str, Enum):
    MULTIPLE_CHOICE = "MULTIPLE_CHOICE_TASK"
    MULTIPLE_RESPONSE = "MULTIPLE_RESPONSE_TASK"
    SHORT_ANSWER = "SHORT_ANSWER_TASK"
    PROGRAMMING = "PROGRAMMING_TASK"


class TaskEvalStatus(str, Enum):
    SUCCESS = "SUCCESS"
    PENDING = "PENDING"
    SKIPPED = "SKIPPED"
    FAILED = "FAILED"


class TaskEvalResult(BaseModel, Generic[TaskResult]):
    task_id: int
    status: TaskEvalStatus
    result: TaskResult | None
    error: str | None = None


class Task(BaseModel, abc.ABC, Generic[TaskUserInput, TaskResult]):
    id: int
    title: str
    description: str | None = None
    type: TaskType
    autograde: bool = True
    order_index: int
    max_attempts: int | None

    @abc.abstractmethod
    def run(self, user_input: TaskUserInput) -> TaskEvalResult[TaskResult]:
        pass

    @abc.abstractmethod
    def validate_user_input(self, user_input: Any) -> TaskUserInput:
        pass

    @abc.abstractmethod
    def redact_private_fields(self):
        pass
