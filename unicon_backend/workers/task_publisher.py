from asyncio.events import AbstractEventLoop
from logging import getLogger
from typing import Final, final

from pika.exchange_type import ExchangeType
from sqlmodel import select

from unicon_backend.constants import (
    AMQP_CONN_NAME,
    AMQP_DEAD_TASK_QUEUE,
    AMQP_DEFAULT_EXCHANGE,
    AMQP_DLX,
    AMQP_RECONNECT_AFTER_SEC,
    AMQP_TASK_QUEUE,
    AMQP_TASK_QUEUE_MSG_TTL_SECS,
    AMQP_URL,
)
from unicon_backend.database import SessionLocal
from unicon_backend.evaluator.tasks.base import TaskEvalStatus
from unicon_backend.lib.amqp import AsyncMQPublisher
from unicon_backend.models.problem import TaskResultORM
from unicon_backend.runner import RunnerJob

logger = getLogger(__name__)


@final
class TaskPublisher(AsyncMQPublisher):
    def __init__(self):
        super().__init__(
            f"{AMQP_CONN_NAME}::publisher",
            AMQP_URL,
            AMQP_DEFAULT_EXCHANGE,
            ExchangeType.topic,
            AMQP_TASK_QUEUE,
            q_msg_ttl_secs=AMQP_TASK_QUEUE_MSG_TTL_SECS,
            dlx_name=AMQP_DLX,
            dlx_routing_key=AMQP_DEAD_TASK_QUEUE,
            reconnect_after_sec=AMQP_RECONNECT_AFTER_SEC,
        )
        self._job_id_dict: dict[int, str] = {}

    def run(self, event_loop: AbstractEventLoop | None = None):
        self._job_id_dict.clear()
        super().run(event_loop)

    def publish_runner_job(self, runner_job: RunnerJob, content_type: str = "application/json"):
        payload = runner_job.model_dump_json(serialize_as_any=True)
        delivery_tag: int = self.publish(payload, content_type)
        self._job_id_dict[delivery_tag] = str(runner_job.id)

    def _delivery_callback(self, delivery_tag: int) -> None:
        job_id: str = self._job_id_dict[delivery_tag]
        del self._job_id_dict[delivery_tag]

        with SessionLocal() as db_session:
            task_result_db = db_session.scalar(
                select(TaskResultORM).where(TaskResultORM.job_id == job_id)
            )
            if task_result_db is None:
                raise ValueError(f"Task with job_id '{job_id}' not found.")
            logger.info("Job pushed: " + str(task_result_db.job_id))

            task_result_db.status = TaskEvalStatus.PENDING
            db_session.add(task_result_db)
            db_session.commit()


task_publisher: Final[TaskPublisher] = TaskPublisher()
