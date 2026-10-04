"""`unicon api` and `unicon openapi`, and the operator's two commands. The
container runs `api` and CI runs `openapi`. The database is migrated by the
forge package's own command, `unicon-forge migrate`.

`unicon create-org` and `unicon create-account` are what only the operator
does, run on the stack itself with the stack's `UNICON_*` settings; no route
does either. `create-org` makes an org whatever `UNICON_ORG_CREATION_OPEN`
says and names its first admin, an existing user at the forge, and refuses
a description over 255 characters before forge is called; it makes the
whole org before it returns, and a step that fails is a refusal like any
other, after which the operator runs it again. `create-account` makes a
person's account at the forge for a deployment whose sign-up is closed, and
prints its first password once. A refusal prints its reason and exits 1.
"""

import argparse
import asyncio
import json
import sys
from collections.abc import Awaitable, Callable
from pathlib import Path

import forge.api
from forge.api import account, log, orgs
from forge.api.errors import UniconError

from unicon.api.v1.auth import CALLBACK_PATH
from unicon.main import create_app
from unicon.schemas.orgs import DESCRIPTION_MAX

REFUSED = 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="unicon", description="The Unicon backend")
    commands = parser.add_subparsers(dest="command", required=True)

    api = commands.add_parser("api", help="serve the HTTP API")
    api.add_argument("--host", default="0.0.0.0")
    api.add_argument("--port", type=int, default=8000)

    openapi = commands.add_parser("openapi", help="write the OpenAPI document")
    openapi.add_argument("--output", type=Path, default=Path("openapi.json"))

    create_org = commands.add_parser("create-org", help="make an org and name its first admin")
    create_org.add_argument("name")
    create_org.add_argument("--admin", required=True, help="an existing user at the forge")
    create_org.add_argument(
        "--description", default="", help=f"at most {DESCRIPTION_MAX} characters"
    )

    create_account = commands.add_parser(
        "create-account", help="make a person's account at the forge"
    )
    create_account.add_argument("username")
    create_account.add_argument("--email", required=True)

    args = parser.parse_args(argv)
    if args.command == "api":
        return _serve(args.host, args.port)
    if args.command == "create-org":
        if len(args.description) > DESCRIPTION_MAX:
            print(
                f"The description is longer than {DESCRIPTION_MAX} characters, "
                "the most the forge takes.",
                file=sys.stderr,
            )
            return REFUSED
        return _as_operator(lambda: _create_org(args.name, args.admin, args.description))
    if args.command == "create-account":
        return _as_operator(lambda: _create_account(args.username, args.email))
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


def _as_operator(command: Callable[[], Awaitable[int]]) -> int:
    """Run one operator command with forge started around it, on the loop
    the server would use.
    """
    log.setup()

    async def run() -> int:
        forge.api.start(callback_path=CALLBACK_PATH)
        try:
            return await command()
        except UniconError as refused:
            print(refused.detail, file=sys.stderr)
            return REFUSED
        finally:
            await forge.api.stop()

    return asyncio.run(run(), loop_factory=event_loop)


async def _create_org(name: str, admin: str, description: str) -> int:
    await orgs.create_by_operator(name, description=description, admin_username=admin)
    print(f"Org {name} made, with {admin} its admin.")
    return 0


async def _create_account(username: str, email: str) -> int:
    user, password = await account.create(username, email=email)
    print(f"Account {user.username} created, user id {user.id}.")
    print(f"First password: {password}")
    print("It is shown only this once and must be changed at the first sign-in.")
    return 0


def _write_openapi(output: Path) -> int:
    document = json.dumps(create_app().openapi(), indent=2, sort_keys=True) + "\n"
    output.write_text(document, encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
