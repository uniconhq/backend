import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.routing import APIRoute

from unicon_backend.constants import CORS_REGEX_WHITELIST, FRONTEND_URL
from unicon_backend.logger import setup_rich_logger
from unicon_backend.routers import auth, file, group, organisation, problem, project, role
from unicon_backend.workers.dead_task_consumer import dead_task_consumer
from unicon_backend.workers.pending_push_collector import pending_push_collector
from unicon_backend.workers.task_publisher import task_publisher
from unicon_backend.workers.task_result_consumer import task_result_consumer

setup_rich_logger()
logging.getLogger("pika").setLevel(logging.WARNING)


@asynccontextmanager
async def lifespan(app: FastAPI):
    _event_loop = asyncio.get_event_loop()
    dead_task_consumer.run(_event_loop)
    task_result_consumer.run(_event_loop)
    task_publisher.run(_event_loop)
    pending_push_collector.run(_event_loop)

    yield

    task_publisher.stop()
    task_result_consumer.stop()
    dead_task_consumer.stop()
    pending_push_collector.stop()


app = FastAPI(title="Unicon 🦄 Backend", lifespan=lifespan, separate_input_output_schemas=False)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_URL],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    **({"allow_origin_regex": CORS_REGEX_WHITELIST} if CORS_REGEX_WHITELIST else {}),
)

app.include_router(auth.router)
app.include_router(problem.router)
app.include_router(organisation.router)
app.include_router(project.router)
app.include_router(role.router)
app.include_router(group.router)
app.include_router(file.router)

# Set `operation_id` for all routes to the same as the `name`
# This is done to make the generated OpenAPI documentation more readable
for route in app.routes:
    if isinstance(route, APIRoute):
        route.operation_id = route.name
