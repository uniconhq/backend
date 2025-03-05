import logging

from pika.exchange_type import ExchangeType

from unicon_backend.constants import (
    AMQP_CONN_NAME,
    AMQP_EXCHANGE_NAME,
    AMQP_TASK_QUEUE_NAME,
    AMQP_URL,
)
from unicon_backend.lib.amqp import AsyncMQPublisher

logger = logging.getLogger(__name__)


class TaskPublisher(AsyncMQPublisher):
    def __init__(self):
        super().__init__(
            f"{AMQP_CONN_NAME}::publisher",
            AMQP_URL,
            AMQP_EXCHANGE_NAME,
            ExchangeType.topic,
            AMQP_TASK_QUEUE_NAME,
        )


task_publisher = TaskPublisher()
