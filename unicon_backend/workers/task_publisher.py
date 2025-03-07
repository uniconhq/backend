from typing import Final, final

from pika.exchange_type import ExchangeType

from unicon_backend.constants import (
    AMQP_CONN_NAME,
    AMQP_DEAD_TASK_QUEUE,
    AMQP_DEFAULT_EXCHANGE,
    AMQP_DLX,
    AMQP_TASK_QUEUE,
    AMQP_TASK_QUEUE_MSG_TTL_SECS,
    AMQP_URL,
)
from unicon_backend.lib.amqp import AsyncMQPublisher


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
        )


task_publisher: Final[TaskPublisher] = TaskPublisher()
