from typing import Any

from unicon_backend.evaluator.tasks.base import Task, TaskEvalResult, TaskEvalStatus
from unicon_backend.evaluator.tasks.programming.base import ProgrammingTask
from unicon_backend.workers.task_publisher import task_publisher


def run_programming_task(task: ProgrammingTask, input: Any) -> TaskEvalResult:
    # NOTE: It is safe to ignore type checking here because the type of task is determined by the "type" field
    # As long as the "type" field is set correctly, the type of task will be inferred correctly
    runner_job = task.create_runner_job(task.validate_user_input(input))  # type: ignore
    task_publisher.publish_runner_job(runner_job)
    return TaskEvalResult(task_id=task.id, status=TaskEvalStatus.PENDING_PUSH, result=runner_job.id)


def run_as_programming_task(task: Task, input: Any) -> TaskEvalResult:
    programming_task = ProgrammingTask.model_validate(task.model_dump())
    return run_programming_task(programming_task, input)
