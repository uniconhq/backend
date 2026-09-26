"""`unicon api`, `unicon migrate` and `unicon openapi`. The container runs the
first two; CI runs all three.
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

from forge.log import configure
from forge.runtime import migrate
from forge.settings import Settings, load_database_settings, load_settings

from unicon.main import create_app


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
        migrate(str(load_database_settings().database_url))
        return 0
    return _write_openapi(args.output)


def _serve(host: str, port: int) -> int:
    import uvicorn

    settings = load_settings()
    configure(settings.log_level)
    _use_selector_loop_on_windows()
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
    """psycopg cannot run asynchronously on Windows' default proactor loop."""
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


def _write_openapi(output: Path) -> int:
    app = create_app(Settings.for_tests())
    document = json.dumps(app.openapi(), indent=2, sort_keys=True) + "\n"
    output.write_text(document, encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
