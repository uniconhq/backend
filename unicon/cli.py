"""`unicon api` and `unicon openapi`. The container runs the first; CI runs
both. The database is migrated by the forge package's own command,
`unicon-forge migrate`.
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

from forge.api import log

from unicon.main import create_app


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="unicon", description="The Unicon backend")
    commands = parser.add_subparsers(dest="command", required=True)

    api = commands.add_parser("api", help="serve the HTTP API")
    api.add_argument("--host", default="0.0.0.0")
    api.add_argument("--port", type=int, default=8000)

    openapi = commands.add_parser("openapi", help="write the OpenAPI document")
    openapi.add_argument("--output", type=Path, default=Path("openapi.json"))

    args = parser.parse_args(argv)
    if args.command == "api":
        return _serve(args.host, args.port)
    return _write_openapi(args.output)


def _serve(host: str, port: int) -> int:
    log.setup()
    import uvicorn

    uvicorn.run(
        create_app(),
        host=host,
        port=port,
        loop=f"{__name__}:event_loop",
        proxy_headers=True,
        forwarded_allow_ips="*",
        access_log=False,
        log_config=None,
    )
    return 0


def event_loop() -> asyncio.AbstractEventLoop:
    """The loop the server runs on, named to uvicorn as a factory: uvicorn
    picks its own loop and ignores the process's policy, so this is the one
    way to choose. psycopg cannot run asynchronously on Windows' default
    proactor loop, so Windows gets the selector loop. Everywhere else it is
    uvicorn's own choice, which is uvloop where that is installed.
    """
    if sys.platform == "win32":
        return asyncio.SelectorEventLoop()
    from uvicorn.loops.auto import auto_loop_factory

    return auto_loop_factory()()


def _write_openapi(output: Path) -> int:
    document = json.dumps(create_app().openapi(), indent=2, sort_keys=True) + "\n"
    output.write_text(document, encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
