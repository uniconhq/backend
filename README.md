# Unicon backend

The HTTP shell over the `forge` package: the routes, the cookies, the Origin
check, the request log and the OpenAPI document, started by `unicon api`. It
imports the package's public surface and nothing else. It has no table, no
migration and no forge client of its own, and it picks the implementation
behind the forge port with `UNICON_FORGE`. This repo produces one container
image and the `openapi.json` at its root, which the frontend generates its
client from.

## Running it

You need [uv](https://docs.astral.sh/uv/), a Postgres, and the `forge`
repository checked out beside this one. Everything below is run from the
repository root.

```sh
uv sync                       # create .venv from uv.lock, forge from ../forge
cp .env.example .env          # then fill it in, or take deploy/.env
set -a; . ./.env; set +a
uv run unicon migrate         # apply the forge package's migrations
uv run unicon api             # http://localhost:8000
```

`GET /healthz` says the process is up. `GET /readyz` says the database
answered. `GET /api/v1/time` is the server clock, the only clock the frontend
trusts. With `UNICON_FORGE=fake` the whole shell runs against the in-memory
forge, with no git host at all.

The real configuration comes from the compose stack in `deploy`, whose
bootstrap writes a `.env` with every `UNICON_*` variable the package's
settings class reads. A missing or malformed variable stops the process at
start with the variable named. Two hostnames in that file are the stack's:
`postgres` in `UNICON_DATABASE_URL` and `forgejo` in
`UNICON_FORGE_INTERNAL_URL`; from a laptop shell substitute the published
addresses.

## Sign-in and sessions

Sign-in is the forge's OpenID Connect. `GET /api/v1/auth/login` asks the
package for the redirect, keeps what checks the answer in the signed
short-lived `unicon_sign_in` cookie, and sends the browser to the forge.
`/callback` hands the code and the cookie's contents back to the package,
receives a session, sets the `unicon_session` cookie and lands on the
validated `next` path. A callback with no sign-in cookie, or a state that does
not match, lands on `/login` with the error's code in the query.

The session cookie carries a random session id and nothing else, signed under
`UNICON_SESSION_SIGNING_KEY` so a forged id is refused without a database
read. Both cookies are `HttpOnly`, `SameSite=Lax`, and `Secure` when
`UNICON_COOKIE_SECURE` is on. The app and the API share one origin, so the
cookie is first-party.

`OriginCheck` refuses any state-changing request carrying the session cookie
whose `Origin`, or the origin of its `Referer`, is not the public URL. That
and `SameSite=Lax` are the whole CSRF story.

`GET /api/v1/me` returns the caller's identity and their roles at every scope.
The session list, revoke, sign-out-everywhere, deactivate and delete routes
each call the matching package operation and return its refusal unchanged.

## Errors

Every error is an RFC 9457 problem document with a stable `code`. The
package's typed errors are mapped to a status in `unicon/api/errors.py` and
nowhere else:

| Code | Status |
|---|---|
| `not_found` | 404 |
| `forbidden`, `fresh_sign_in_required`, `origin_mismatch` | 403 |
| `conflict`, `sole_admin`, `shared_workflow_owner` | 409 |
| `rejected`, `validation_error` | 422 |
| `unauthenticated`, `session_expired` | 401, and the session cookie is cleared |
| `sign_in_invalid`, `sign_in_denied` | 400 |
| `forge_misconfigured` | 502 |
| `forge_unavailable` | 503 |

`sole_admin` carries `scopes` and `shared_workflow_owner` carries
`workflows`, so the browser can show what stands in the way.

## Logging

Every line `unicon api` writes is one JSON record through the package's
logger. Every request produces one `http.request` record with `method`,
`path`, `status` and `duration_ms`, and nothing from the request itself: not
the query string, not the cookie, not the body. `UNICON_LOG_LEVEL` sets the
level.

## Checks

What CI runs, in the same order:

```sh
uv sync --frozen
uv run ruff format --check .
uv run ruff check .
uv run lint-imports
uv run mypy
UNICON_TEST_DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/postgres uv run pytest
UNICON_DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/unicon uv run unicon migrate
uv run unicon openapi && git diff --exit-code openapi.json
docker build -f backend/Dockerfile ..
```

`lint-imports` holds the two contracts that keep this a shell: nothing here
imports the package's `db` or anything under its `forges`. The integration
tests run the app over a real Postgres and the in-memory forge; they create
and drop a database of their own on the server the URL names and are skipped
without it. The openapi diff fails when a response changed and nobody
regenerated the document.

The image is built from the parent directory with both `backend/` and
`forge/` checked out, because the package is installed from the sibling path
until the backend pins a released version of it.

## Layout

```
unicon/
  main.py      the app factory; the runtime starts and stops with the app
  cli.py       api | migrate | openapi
  api/         routes, cookies, the error mapping and the middleware
  schemas/     what the API answers with, including the problem document
tests/
  unit/        no database
  integration/ a real Postgres and the in-memory forge
```

## Licence

MIT. See `LICENSE`.
