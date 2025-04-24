import asyncio
from asyncio.events import AbstractEventLoop
from datetime import timedelta
from logging import getLogger
from typing import Final, final

import sqlalchemy as sa
from sqlmodel import select

from unicon_backend.constants import (
    PENDING_PUSH_COLLECTOR_CHECK_INTERVAL,
    PENDING_PUSH_TIMEOUT,
)
from unicon_backend.database import SessionLocal
from unicon_backend.evaluator.tasks.base import TaskEvalStatus
from unicon_backend.models.problem import TaskResultORM

logger = getLogger(__name__)


@final
class PendingPushCollector:
    def __init__(
        self,
        check_interval: int = PENDING_PUSH_COLLECTOR_CHECK_INTERVAL,
        timeout: int = PENDING_PUSH_TIMEOUT,
    ):
        self._check_interval: int = check_interval
        self._timeout: int = timeout
        self._stop: bool = False

    def _collect_sync(self):
        with SessionLocal() as db_session:
            task_results = db_session.scalars(
                select(TaskResultORM)
                .where(TaskResultORM.status == TaskEvalStatus.PENDING_PUSH)
                .where(sa.func.now() - TaskResultORM.started_at > timedelta(seconds=self._timeout))
            ).all()
            for task_result in task_results:
                task_result.status = TaskEvalStatus.FAILED
                task_result.completed_at = sa.func.now()  # type: ignore[assignment]
                logger.info(task_result)
                db_session.add(task_result)
            db_session.commit()

    async def _collect(self):
        logger.info("Collecting pending push task results...")
        await self.event_loop.run_in_executor(None, self._collect_sync)
        logger.info("Done")

    async def _task(self):
        while not self._stop:
            await self._collect()
            await asyncio.sleep(self._check_interval)

    def run(self, event_loop: AbstractEventLoop):
        self._stop = False
        self.event_loop = event_loop
        self.event_loop.create_task(self._task())
        logger.info("Started")

    def stop(self):
        self._stop = True
        logger.info("Stopped")


pending_push_collector: Final[PendingPushCollector] = PendingPushCollector()
