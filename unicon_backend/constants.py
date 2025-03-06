import os
from typing import Final

from dotenv import load_dotenv

load_dotenv()


def _get_env_var(name: str, default: str | None = None, required: bool = True):
    value = os.getenv(name, default) or default
    if (value is None) and required:
        raise ValueError(f"{name} environment variable not defined")
    return value


DATABASE_URL: Final[str] = _get_env_var("DATABASE_URL")

FRONTEND_URL: Final[str] = _get_env_var("FRONTEND_URL", "http://localhost:5173")
CORS_REGEX_WHITELIST: Final[str | None] = _get_env_var("CORS_REGEX_WHITELIST", required=False)

SECRET_KEY: Final[str] = _get_env_var("SECRET_KEY", "")

AMQP_URL: Final[str] = _get_env_var("AMQP_URL")
AMQP_DEFAULT_EXCHANGE: Final[str] = _get_env_var("AMQP_DEFAULT_EXCHANGE", "unicon")
AMQP_TASK_QUEUE: Final[str] = _get_env_var("AMQP_TASK_QUEUE", "unicon.tasks")
_task_q_ttl_str: Final[str | None] = _get_env_var("AMQP_TASK_QUEUE_MSG_TTL_SECS", required=False)
AMQP_TASK_QUEUE_MSG_TTL_SECS: Final[int | None] = int(_task_q_ttl_str) if _task_q_ttl_str else None
AMQP_RESULT_QUEUE: Final[str] = _get_env_var("AMQP_RESULT_QUEUE", "unicon.results")
AMQP_CONN_NAME: Final[str] = _get_env_var("AMQP_CONN_NAME", "unicon-backend")

AMQP_DLX: Final[str] = _get_env_var("AMQP_DLX", "unicon.dlx")
AMQP_DEAD_TASK_QUEUE: Final[str] = _get_env_var("AMQP_DEAD_TASK_QUEUE", "unicon.tasks.dead")

PERMIFY_HOST: Final[str] = _get_env_var("PERMIFY_HOST", "http://localhost:3476")
PERMIFY_SCHEMA_VERSION: Final[str | None] = _get_env_var("PERMIFY_SCHEMA_VERSION", required=False)
PERMIFY_TENANT_ID: Final[str] = _get_env_var("PERMIFY_TENANT_ID", "t1")

MINIO_HOST: Final[str] = _get_env_var("MINIO_HOST", "localhost:9000")
MINIO_ACCESS_KEY: Final[str] = _get_env_var("MINIO_ACCESS_KEY")
MINIO_SECRET_KEY: Final[str] = _get_env_var("MINIO_SECRET_KEY")
MINIO_BUCKET = _get_env_var("MINIO_BUCKET", "unicon")
