import abc
from asyncio import AbstractEventLoop
from logging import getLogger
from typing import Literal

import pika
from pika.adapters.asyncio_connection import AsyncioConnection
from pika.channel import Channel
from pika.delivery_mode import DeliveryMode
from pika.exchange_type import ExchangeType
from pika.frame import Method
from pika.spec import Basic, BasicProperties

logger = getLogger(__name__)


class AsyncMQBase(abc.ABC):
    def __init__(
        self,
        conn_name: str,
        amqp_url: str,
        ex_name: str,
        ex_type: ExchangeType,
        q_name: str,
        routing_key: str | None = None,
        dlx_name: str | None = None,
        dlx_routing_key: str | None = None,
    ):
        self._conn_params = pika.URLParameters(amqp_url)
        self._conn_params.client_properties = {"connection_name": conn_name}

        self.ex_name = ex_name
        self.ex_type = ex_type

        self.q_name = q_name
        self.routing_key = routing_key or q_name
        self.dlx_name = dlx_name
        self.dlx_routing_key = dlx_routing_key

        # Connection state
        self._conn: AsyncioConnection | None = None
        self._chan: Channel | None = None
        self._closing: bool = False

    def run(self, event_loop: AbstractEventLoop | None = None):
        self._conn = AsyncioConnection(
            parameters=self._conn_params,
            on_open_callback=self._on_conn_open,
            on_open_error_callback=self._on_conn_open_error,
            on_close_callback=self._on_conn_closed,
            # If there is no event loop, `pika` will create one
            custom_ioloop=event_loop,
        )

    def stop(self):
        self._closing = True
        if self._chan:
            self._chan.close()
        if self._conn:
            self._conn.close()

    def _on_conn_open(self, _conn: AsyncioConnection):
        self._open_chan()

    def _on_conn_open_error(self, _conn: AsyncioConnection, err: BaseException):
        logger.error(f"Connection open error: {err}")

    def _on_conn_closed(self, _conn: AsyncioConnection, err: BaseException):
        self._chan = None
        if not self._closing:
            # If the connection was closed unexpectedly
            logger.error(f"Connection closed unexpectedly: {err}")

    def _close_conn(self):
        if self._conn and not (self._conn.is_closing or self._conn.is_closed):
            self._conn.close()

    def _open_chan(self):
        if self._conn:
            self._conn.channel(on_open_callback=self._on_chan_open)

    def _on_chan_open(self, chan: Channel):
        self._chan = chan
        self._chan.add_on_close_callback(self._on_chan_closed)
        self._setup_ex()

    def _on_chan_closed(self, _chan: Channel, _reason: BaseException):
        self._close_conn()

    def _setup_ex(self):
        if self._chan:
            self._chan.exchange_declare(self.ex_name, self.ex_type, callback=self._on_ex_declare_ok)

    def _on_ex_declare_ok(self, _frame: Method):
        self._setup_queue()

    def _setup_queue(self):
        if self._chan:
            queue_args: dict[str, str] = {}
            if self.dlx_name and self.dlx_routing_key:
                queue_args["x-dead-letter-exchange"] = self.dlx_name
                queue_args["x-dead-letter-routing-key"] = self.dlx_routing_key

            self._chan.queue_declare(
                self.q_name, callback=self._on_queue_declare_ok, durable=True, arguments=queue_args
            )

    def _on_queue_declare_ok(self, _frame: Method):
        if self._chan:
            self._chan.queue_bind(
                self.q_name, self.ex_name, self.routing_key, callback=self._on_queue_bind_ok
            )

    @abc.abstractmethod
    def _on_queue_bind_ok(self, _frame: Method):
        """Handle successful queue binding - to be implemented by subclasses."""
        ...


from dataclasses import dataclass


@dataclass
class AsyncMQConsumeMessageResult:
    success: bool
    requeue: bool  # Ignored if success is True


class AsyncMQConsumer(AsyncMQBase):
    def __init__(
        self,
        conn_name: str,
        amqp_url: str,
        ex_name: str,
        ex_type: ExchangeType,
        q_name: str,
        routing_key: str | None = None,
        dlx_name: str | None = None,
        dlx_routing_key: str | None = None,
    ):
        super().__init__(
            conn_name, amqp_url, ex_name, ex_type, q_name, routing_key, dlx_name, dlx_routing_key
        )

        self._consume_tag: str | None = None
        self._consuming: bool = False

    def _on_queue_bind_ok(self, _frame: Method):
        self._set_qos()

    def _set_qos(self):
        if self._chan:
            self._chan.basic_qos(prefetch_count=1, callback=self._on_qos_ok)

    def _on_qos_ok(self, _frame: Method):
        self._start_consuming()

    def _start_consuming(self):
        if self._chan:
            self._chan.add_on_cancel_callback(self._on_consumer_cancelled)
            self._consumer_tag = self._chan.basic_consume(self.q_name, self._on_message)
            self._consuming = True

    def _stop_consuming(self):
        if self._chan and self._consumer_tag:
            self._chan.basic_cancel(self._consumer_tag, callback=self._on_cancel_ok)

    def _on_consumer_cancelled(self, _frame: Method):
        # This differs from `_on_cancel_ok` in that it is called when the consumer is cancelled by the server
        # (e.g. when the queue is deleted)
        if self._chan:
            self._chan.close()

    def _on_cancel_ok(self, _frame: Method):
        if self._chan:
            self._consuming = False
            self._chan.close()

    @abc.abstractmethod
    def _message_callback(
        self, basic_deliver: Basic.Deliver, properties: BasicProperties, body: bytes
    ) -> AsyncMQConsumeMessageResult: ...

    def _on_message(
        self,
        _chan: Channel,
        basic_deliver: Basic.Deliver,
        properties: BasicProperties,
        body: bytes,
    ):
        assert self._chan is not None
        result = self._message_callback(basic_deliver, properties, body)
        if result.success:
            self._chan.basic_ack(basic_deliver.delivery_tag)
        else:
            self._chan.basic_nack(basic_deliver.delivery_tag, requeue=result.requeue)

    def stop(self):
        if not self._closing:
            self._closing = True
            if self._consuming:
                self._stop_consuming()
            else:
                super().stop()


class AsyncMQPublisher(AsyncMQBase):
    def __init__(
        self,
        conn_name: str,
        amqp_url: str,
        ex_name: str,
        ex_type: ExchangeType,
        q_name: str,
        routing_key: str | None = None,
        dlx_name: str | None = None,
        dlx_routing_key: str | None = None,
    ):
        super().__init__(
            conn_name, amqp_url, ex_name, ex_type, q_name, routing_key, dlx_name, dlx_routing_key
        )

        self._deliveries: dict[int, Literal[True]] = {}
        self._acked: int = 0  # Number of messages acknowledged
        self._nacked: int = 0  # Number of messages rejected
        self._message_number: int = 0  # Number of messages published

    def _on_queue_bind_ok(self, _frame):
        if self._chan:
            self._chan.confirm_delivery(self._on_delivery_confirmation)

    def _on_delivery_confirmation(self, frame: Method):
        assert isinstance(frame.method, Basic.Ack | Basic.Nack)

        confirmation_type = frame.method.NAME.split(".")[1].lower()
        ack_multiple = frame.method.multiple
        delivery_tag = frame.method.delivery_tag

        self._acked += confirmation_type == "ack"
        self._nacked += confirmation_type == "nack"

        del self._deliveries[delivery_tag]

        if ack_multiple:
            for tmp_tag in filter(lambda tmp_tag: tmp_tag <= delivery_tag, self._deliveries):
                self._acked += 1
                del self._deliveries[tmp_tag]

    def publish(self, payload: str, content_type: str = "application/json"):
        if self._chan:
            self._chan.basic_publish(
                self.ex_name,
                self.routing_key,
                payload,
                properties=BasicProperties(
                    content_type=content_type, delivery_mode=DeliveryMode.Persistent
                ),
            )
            # Mark that the message was published for delivery confirmation
            self._message_number += 1
            self._deliveries[self._message_number] = True

    def run(self, event_loop: AbstractEventLoop | None = None):
        self._deliveries.clear()
        self._acked = 0
        self._nacked = 0
        self._message_number = 0
        super().run(event_loop)
