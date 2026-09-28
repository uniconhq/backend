# Unicon backend

The HTTP shell over the `forge` package: the routes, the response schemas,
the cookie names and flags, the Origin check, the request log, the table from
error to status code, and the OpenAPI document, started by `unicon api`. It
imports `forge.api`, the package's front door, and nothing else of it. It has
no table, no migration, no transaction, no setting, no signing key and no
forge client of its own; forge picks the implementation behind its port with
`UNICON_FORGE`. This repo produces one container
image and the `openapi.json` at its root, which the frontend generates its
client from.

## Running it

You need [uv](https://docs.astral.sh/uv/) and a Postgres. Everything below
is run from the repository root.

```sh
uv sync                       # create .venv from uv.lock
cp .env.example .env          # then fill it in, or take deploy/.env
set -a; . ./.env; set +a
uv run unicon-forge migrate   # the forge package's command, installed with it
uv run unicon api             # http://localhost:8000
```

`GET /openapi.json` is the document the frontend generates from; the Swagger
and ReDoc pages are off, since an API browser is not part of what a
deployment exposes. `GET /healthz` says the process is up. `GET /readyz` says the database
answered. `GET /api/v1/time` is the server clock, the only clock the frontend
trusts. With `UNICON_FORGE=fake` the whole shell runs against the in-memory
forge, with no git host at all.

The database is migrated by the forge package, not by this shell: the
package installs `unicon-forge`, and `unicon-forge migrate` reads
`UNICON_DATABASE_URL`, applies the migrations and exits. The stack runs it
from this image before the API starts.

The real configuration comes from the compose stack in `deploy`, whose
bootstrap writes a `.env` with every `UNICON_*` variable. Every one of them is
read by forge, `UNICON_SESSION_SIGNING_KEY` and `UNICON_COOKIE_SECURE`
included; this shell reads none. `unicon api` calls `forge.api.log.setup()`
first, before the server starts, so every line is JSON, and the app's
lifespan calls `forge.api.start(callback_path="/api/v1/auth/callback")`,
giving forge the one thing it cannot know, this shell's callback route. A
missing or malformed variable stops the process at start with the variable
named. `unicon openapi` builds the app without starting forge, so it reads no
setting; the Origin check asks forge for the public URL on the first request
it checks. Two hostnames in that file are the stack's:
`postgres` in `UNICON_DATABASE_URL` and `forgejo` in
`UNICON_FORGE_INTERNAL_URL`; from a laptop shell substitute the published
addresses.

## Sign-in and sessions

Sign-in is the forge's OpenID Connect. `GET /api/v1/auth/login` asks the
package for the redirect, keeps what checks the answer in the signed
short-lived `unicon_sign_in` cookie, and sends the browser to the forge.
`/callback` hands the code, the cookie's contents and the session the browser
already had to `sign_in.complete`, which creates the new session and ends the
old one in one transaction; the route sets the `unicon_session` cookie and
lands on the `next` path forge validated when the sign-in started. A callback with no sign-in cookie, or a state that does
not match, lands on `/login` with the error's code in the query.

What goes into the two cookies is forge's: `forge.api.cookies` makes the
signed value and reads it back, and the signing key never leaves the package.
The session cookie carries a random session id and nothing else, so a forged
id is refused without a database read. This shell keeps the names, the
`Set-Cookie` header and the flags: both cookies are `HttpOnly` and
`SameSite=Lax`, and `Secure` as forge's `cookies.policy()` says, which is on
whenever the public URL is https. The app and the API share one origin, so
the cookie is first-party.

`OriginCheck` refuses any state-changing request whose `Origin`, or the
origin of its `Referer`, is not the public URL, whether or not it carries a
session. That and `SameSite=Lax` are the whole CSRF story.

`GET /api/v1/me` returns the caller's identity and their roles at every scope.
The session list, revoke, sign-out-everywhere, deactivate and delete routes
each call the matching forge action and return its refusal unchanged.

An action is one unit of work, and a route calls one per request. The action
opens its own transaction, commits before it returns and rolls back when it
raises, so by the time the route builds a 204 or a redirect the change is on
disk, and an action whose commit fails raises out of the call and is answered
as a 500. The one dependency, `CurrentSession`, reads the cookie and calls
`identity.current`. This shell never sees a transaction.

`GET /readyz` answers 503 `{"status": "not_ready"}` when forge says the
database did not answer; what failed is in forge's log and not in the
answer.

## Errors

Every error is an RFC 9457 problem document with a stable `code`. The
package's typed errors are mapped to a status in `unicon/api/errors.py` and
nowhere else:

| Code | Status |
|---|---|
| `not_found` | 404 |
| `forbidden`, `fresh_sign_in_required`, `origin_mismatch` | 403 |
| `conflict`, `sole_admin`, `shared_workflow_owner` | 409 |
| `rejected`, `invalid_name`, `validation_error` | 422 |
| `unauthenticated`, `session_expired` | 401, and the session cookie is cleared |
| `sign_in_invalid`, `sign_in_denied` | 400 |
| `forge_misconfigured` | 502 |
| `forge_unavailable` | 503 |

`sole_admin` carries `scopes` and `shared_workflow_owner` carries
`workflows`, so the browser can show what stands in the way. A refusal
carries its `detail`, which is the reason the person can act on.
`forge_unavailable` and `forge_misconfigured` are answered with a fixed
sentence and their detail, which names the forge's hosts and paths, goes to
the log as `errors.forge`. A typed error the table does not know is a fault
in the table: it is answered as a 500 with its code and a fixed sentence, and
logged as `errors.unmapped`.

## Logging

Every line `unicon api` writes is one JSON record, uvicorn's included:
`forge.api.log.setup()` runs first and reads `UNICON_LOG_LEVEL`, and this
shell writes through `forge.api.log.get_logger`. Every request produces one `http.request` record with `method`,
`path`, `status` and `duration_ms`, and nothing from the request itself: not
the query string, not the cookie, not the body.

## Checks

What CI runs, in the same order:

```sh
uv sync --frozen
uv run ruff format --check .
uv run ruff check .
uv run lint-imports
uv run mypy
UNICON_TEST_DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/postgres uv run pytest
UNICON_DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/unicon uv run unicon-forge migrate
uv run unicon openapi && git diff --exit-code openapi.json
docker build .
```

`lint-imports` holds the two rules that keep this a shell. The first, over
`unicon/` and `tests/`, forbids every part of forge but its front door and
test kit, and `sqlalchemy`, so the backend reaches forge through `forge.api`
alone; when something it needs is missing there, it is added there in a
forge pull request, never reached for deeper. The second forbids
`forge.testing` in `unicon/`, so the running app never loads the test kit.
The tests load that kit as a pytest plugin, import from it what they arrange
the fake with, and run the app over the same migrated Postgres, in-memory
forge and setup the package tests itself with, held by `held_setup`; they
create and drop a database of their own on the server the URL names and are
skipped without it. The openapi diff fails when a response changed and nobody
regenerated the document.

The `forge` package comes from one release, named in `[tool.uv.sources]`
and locked to the wheel's hash in `uv.lock`, so a change in that repository
reaches this one only when someone moves the pin. Moving it is one edit
followed by `uv lock`, and it carries both the code and the migrations
`unicon-forge migrate` applies.

## Layout

```
unicon/
  main.py      the app factory; forge starts and stops with the app
  cli.py       api | openapi
  api/         routes, the session dependency, cookie names and flags, the error
               mapping and the middleware
  schemas/     what the API answers with, including the problem document
tests/
  unit/        no database
  integration/ a real Postgres and the in-memory forge, through the browser's hops
```

## Licence

MIT. See `LICENSE`.
