from typing import Final, final

import pika
from pika.exchange_type import ExchangeType
from pika.spec import Basic
from sqlalchemy import func
from sqlmodel import select

from unicon_backend.constants import (
    AMQP_CONN_NAME,
    AMQP_DEAD_TASK_QUEUE,
    AMQP_DLX,
    AMQP_URL,
)
from unicon_backend.database import SessionLocal
from unicon_backend.evaluator.tasks.base import TaskEvalStatus
from unicon_backend.lib.amqp import AsyncMQConsumeMessageResult, AsyncMQConsumer
from unicon_backend.models.problem import TaskResultORM
from unicon_backend.runner import RunnerJob


@final
class DeadTasksConsumer(AsyncMQConsumer):
    def __init__(self):
        super().__init__(
            f"{AMQP_CONN_NAME}::dead-task-consumer",
            AMQP_URL,
            AMQP_DLX,
            ExchangeType.direct,
            AMQP_DEAD_TASK_QUEUE,
        )

    def _message_callback(
        self, _basic_deliver: Basic.Deliver, _properties: pika.BasicProperties, body: bytes
    ) -> AsyncMQConsumeMessageResult:
        failed_job = RunnerJob.model_validate_json(body)
        with SessionLocal() as db_session:
            task_result_db = db_session.scalar(
                select(TaskResultORM).where(TaskResultORM.job_id == str(failed_job.id))
            )

            if task_result_db is None:
                # We have received a result a task that we are not aware of
                # NOTE: For now, we just ignore it and ACK accordingly. Ideally we should set up a dead-letter
                # queue for this
                return AsyncMQConsumeMessageResult(success=True, requeue=False)

            task_result_db.status = TaskEvalStatus.FAILED
            task_result_db.completed_at = func.now()  # type: ignore

            db_session.add(task_result_db)
            db_session.commit()
        return AsyncMQConsumeMessageResult(success=True, requeue=False)


dead_task_consumer: Final[DeadTasksConsumer] = DeadTasksConsumer()
