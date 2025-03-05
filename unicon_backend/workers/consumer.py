import json
import logging
from operator import attrgetter
from typing import TYPE_CHECKING, Any, cast

import pika
from pika.exchange_type import ExchangeType
from pika.spec import Basic
from sqlmodel import func, select

from unicon_backend.constants import (
    AMQP_CONN_NAME,
    AMQP_EXCHANGE_NAME,
    AMQP_RESULT_QUEUE_NAME,
    AMQP_URL,
)
from unicon_backend.database import SessionLocal
from unicon_backend.evaluator.tasks.programming.base import (
    ProgrammingTask,
    SocketResult,
    TaskEvalStatus,
    TestcaseResult,
)
from unicon_backend.lib.amqp import AsyncMQConsumeMessageResult, AsyncMQConsumer
from unicon_backend.models.problem import TaskResultORM
from unicon_backend.runner import JobResult, ProgramResult, Status

if TYPE_CHECKING:
    from unicon_backend.evaluator.tasks.programming.base import Testcase
    from unicon_backend.evaluator.tasks.programming.steps import OutputStep

logger = logging.getLogger(__name__)


class TaskResultsConsumer(AsyncMQConsumer):
    def __init__(self):
        super().__init__(
            f"{AMQP_CONN_NAME}::consumer",
            AMQP_URL,
            AMQP_EXCHANGE_NAME,
            ExchangeType.topic,
            AMQP_RESULT_QUEUE_NAME,
        )

    def _message_callback(
        self, _basic_deliver: Basic.Deliver, _properties: pika.BasicProperties, body: bytes
    ) -> AsyncMQConsumeMessageResult:
        response: JobResult = JobResult.model_validate_json(body)
        with SessionLocal() as db_session:
            task_result_db = db_session.scalar(
                select(TaskResultORM).where(TaskResultORM.job_id == str(response.id))
            )

            if task_result_db is None:
                # We have received a result a task that we are not aware of
                # TODO: We should either logged this somewhere or sent to a dead-letter exchange
                return

            task = cast(ProgrammingTask, task_result_db.task_attempt.task.to_task())
            testcases: list[Testcase] = sorted(task.testcases, key=attrgetter("order_index"))
            eval_results: list[ProgramResult] = sorted(
                response.results, key=attrgetter("order_index")
            )

            testcase_results: list[TestcaseResult] = []
            for testcase, eval_result in zip(testcases, eval_results, strict=False):
                output_step: OutputStep = testcase.output_step
                eval_value: dict[str, Any] = {}
                try:
                    eval_value = json.loads(eval_result.stdout)
                except json.JSONDecodeError:
                    if len(eval_result.stdout) > 0:
                        logger.error(
                            f"Failed to decode stdout as JSON for task {task.id} testcase {testcase.id}: {eval_result.stdout}"
                        )

                socket_results: list[SocketResult] = []
                for socket in output_step.data_in:
                    eval_socket_value = eval_value.get(socket.id, None)
                    # If there is no comparison required, the value is always regarded as correct
                    is_correct = (
                        socket.comparison.compare(eval_socket_value) if socket.comparison else True
                    )
                    socket_results.append(
                        SocketResult(id=socket.id, value=eval_socket_value, correct=is_correct)
                    )

                testcase_result = TestcaseResult(**eval_result.model_dump(), results=socket_results)
                if testcase_result.status == Status.OK:
                    testcase_result.status = (
                        Status.WA
                        if not all(socket_result.correct for socket_result in socket_results)
                        else testcase_result.status
                    )
                testcase_results.append(testcase_result)

            task_result_db.status = TaskEvalStatus.SUCCESS
            task_result_db.completed_at = func.now()  # type: ignore
            task_result_db.result = [
                testcase_result.model_dump() for testcase_result in testcase_results
            ]

            db_session.add(task_result_db)
            db_session.commit()

        return AsyncMQConsumeMessageResult(success=True, requeue=False)


task_results_consumer = TaskResultsConsumer()
