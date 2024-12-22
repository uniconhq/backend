import json
import logging
from typing import cast

import pika
import sqlalchemy as sa
from pika.exchange_type import ExchangeType
from pika.spec import Basic
from sqlmodel import select

from unicon_backend.constants import EXCHANGE_NAME, RABBITMQ_URL, RESULT_QUEUE_NAME
from unicon_backend.database import SessionLocal
from unicon_backend.evaluator.tasks.base import TaskEvalStatus
from unicon_backend.evaluator.tasks.programming.steps import (
    OutputStep,
    ProcessedResult,
    SocketResult,
    StepType,
)
from unicon_backend.evaluator.tasks.programming.task import ProgrammingTask
from unicon_backend.lib.amqp import AsyncConsumer
from unicon_backend.models.problem import TaskResultORM
from unicon_backend.runner import JobResult, Status

logging.getLogger("pika").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


class TaskResultsConsumer(AsyncConsumer):
    def __init__(self):
        super().__init__(RABBITMQ_URL, EXCHANGE_NAME, ExchangeType.topic, RESULT_QUEUE_NAME)

    def message_callback(
        self, _basic_deliver: Basic.Deliver, _properties: pika.BasicProperties, body: bytes
    ):
        response: JobResult = JobResult.model_validate_json(body)
        with SessionLocal() as db_session:
            task_result = db_session.scalar(
                select(TaskResultORM).where(TaskResultORM.job_id == response.id)
            )
            if task_result is not None:
                task_result.status = TaskEvalStatus.SUCCESS
                task_result.completed_at = sa.func.now()  # type: ignore

                # Evaluate result based on OutputStep
                task = cast(ProgrammingTask, task_result.task_attempt.task.to_task())

                # Assumption: testcase index = result index
                # Updates to testcases must be done very carefully because of this assumption.
                # To remove this assumption, we need to add a testcase_id field to the result model.
                processedResults: list[ProcessedResult] = []
                for testcase in task.testcases:
                    result = [
                        testcaseResult
                        for testcaseResult in response.results
                        if testcaseResult.id == testcase.id
                    ][0]

                    output_step = OutputStep.model_validate(
                        [node for node in testcase.nodes if node.type == StepType.OUTPUT][0],
                        from_attributes=True,
                    )
                    actual_output = json.loads(result.stdout)

                    socket_results: list[SocketResult] = []
                    for socket in output_step.data_in:
                        socket_result = SocketResult(
                            id=socket.id, value=actual_output.get(socket.id, None), correct=True
                        )
                        if socket.comparison is not None:
                            socket_result.correct = socket.comparison.compare(socket_result.value)

                        if not socket_result.correct and result.status == Status.OK:
                            result.status = Status.WA

                        socket_results.append(socket_result)

                    processedResults.append(
                        ProcessedResult.model_validate(
                            {**result.model_dump(), "results": socket_results}
                        )
                    )

                task_result.result = [result.model_dump() for result in processedResults]

                db_session.add(task_result)
                db_session.commit()


task_results_consumer = TaskResultsConsumer()
