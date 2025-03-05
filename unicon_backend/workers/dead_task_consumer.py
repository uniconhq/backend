from typing import Final, final

import pika
from pika.exchange_type import ExchangeType
from pika.spec import Basic

from unicon_backend.constants import (
    AMQP_CONN_NAME,
    AMQP_DEAD_TASK_QUEUE,
    AMQP_DLX,
    AMQP_URL,
)
from unicon_backend.lib.amqp import AsyncMQConsumeMessageResult, AsyncMQConsumer


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
        return AsyncMQConsumeMessageResult(success=True, requeue=False)


dead_task_consumer: Final[DeadTasksConsumer] = DeadTasksConsumer()
