"""`unicon api`, `unicon migrate`, `unicon openapi`. The container runs the first
two; CI runs all three.
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

from unicon.db.migrations import upgrade_to_head
from unicon.log import configure
from unicon.main import create_app
from unicon.settings import DatabaseSettings, Settings, load_database_settings, load_settings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="unicon", description="The Unicon backend")
    commands = parser.add_subparsers(dest="command", required=True)

    api = commands.add_parser("api", help="serve the HTTP API")
    api.add_argument("--host", default="0.0.0.0")
    api.add_argument("--port", type=int, default=8000)

    commands.add_parser("migrate", help="bring the database up to the latest migration")

    openapi = commands.add_parser("openapi", help="write the OpenAPI document")
    openapi.add_argument("--output", type=Path, default=Path("openapi.json"))

    args = parser.parse_args(argv)
    if args.command == "api":
        return _serve(args.host, args.port)
    if args.command == "migrate":
        return _migrate(load_database_settings())
    return _write_openapi(args.output)


def _serve(host: str, port: int) -> int:
    import uvicorn

    settings = load_settings()
    configure(settings.log_level)
    _use_selector_loop_on_windows()
    # log_config=None leaves uvicorn's loggers on the root handler above, so its
    # own lines are JSON records like everything else. The access log stays off:
    # the request record comes from the RequestLog middleware, which never
    # writes the query string.
    uvicorn.run(
        create_app(settings),
        host=host,
        port=port,
        proxy_headers=True,
        forwarded_allow_ips="*",
        access_log=False,
        log_config=None,
    )
    return 0


def _use_selector_loop_on_windows() -> None:
    """psycopg cannot run asynchronously on Windows' default proactor loop.
    Deployment is Linux; this is for a laptop.
    """
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


def _migrate(settings: DatabaseSettings) -> int:
    upgrade_to_head(str(settings.database_url))
    return 0


def _write_openapi(output: Path) -> int:
    app = create_app(Settings.for_tests())
    document = json.dumps(app.openapi(), indent=2, sort_keys=True) + "\n"
    output.write_text(document, encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
