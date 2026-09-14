# Unicon backend

The API behind Unicon. It holds nine tables of its own and reads everything
else live from Forgejo: accounts, organisations, repositories, tags and issues
are Forgejo objects, grading runs are Woodpecker pipelines, and large files
sit in Garage. This repo produces one container image and the `openapi.json`
at its root, which the frontend generates its client from.

## Running it

You need Docker and [uv](https://docs.astral.sh/uv/). Everything below is run
from the repository root.

```sh
uv sync                       # create .venv from uv.lock
docker run -d --name unicon-dev-db -e POSTGRES_PASSWORD=dev -p 5440:5432 postgres:16-alpine
cp .env.example .env          # then fill it in, or take deploy/.env (see below)
set -a; . ./.env; set +a
uv run unicon migrate         # bring the database up to date
uv run unicon api             # http://localhost:8000
```

`GET /healthz` says the process is up. `GET /readyz` says Postgres answered.
`GET /api/v1/time` is the server clock, which is the only clock the UI trusts.

The real configuration comes from the compose stack in `deploy`, whose
bootstrap script writes a `.env` with every `UNICON_*` variable the settings
class reads. Missing or malformed values stop the process at startup with the
variable named.

That file is written for containers, so two of its hostnames mean nothing from
a laptop shell: `postgres` in `UNICON_DATABASE_URL` is the stack's Postgres,
reachable at whatever host and port the dev override publishes, and
`UNICON_FORGE_INTERNAL_URL=http://forgejo:3000` is Forgejo, which the browser
and a local process both reach at `http://localhost:3300`. Substitute those two
and the rest of the file works as it stands.

`UNICON_LOG_LEVEL` (default `INFO`) sets the level for `unicon api`. Nothing
logs a token, an authorization code or a PKCE verifier at any level; a failed
login logs its outcome code and the first eight characters of the state. The
per-request access log is off for the same reason: uvicorn writes the whole
request line, and `/api/v1/auth/callback?code=...` is a request line with a
credential in it. The proxy in front keeps the traffic record.

## Checks

What CI runs, in the same order, so a red build can be reproduced here:

```sh
uv sync --frozen
uv run ruff format --check .
uv run ruff check .
uv run lint-imports
uv run mypy
uv run pytest tests/unit
UNICON_TEST_DATABASE_URL=postgresql+psycopg://postgres:dev@localhost:5440/postgres uv run pytest tests/integration
UNICON_DATABASE_URL=postgresql+psycopg://postgres:dev@localhost:5440/unicon uv run unicon migrate
UNICON_DATABASE_URL=postgresql+psycopg://postgres:dev@localhost:5440/unicon uv run alembic check
uv run unicon openapi && git diff --exit-code openapi.json
docker build .
```

`alembic check` is the step that fails when a model changed and nobody wrote a
migration. The openapi diff is the step that fails when a response model
changed and nobody regenerated the document; run `uv run unicon openapi` and
commit the result.

Integration tests need a real Postgres; they create and drop a database of
their own on the server that URL points at, so it must be one you do not mind
them writing to. Port 5440 in the examples above is the throwaway container
from the previous section: the compose stack in `deploy` already holds 5432.
Without the variable those tests are skipped, which is why unit and
integration tests are two commands.

## Login and sessions

People sign in with their Forgejo account. Clicking Sign in is a full-page
navigation to `/api/v1/auth/login`, which sends the browser to Forgejo with a
random state and a PKCE challenge. Forgejo asks for the password, any second
factor, and consent the first time. It sends the browser back to
`/api/v1/auth/callback`, where the backend checks the state, exchanges the code
for a token pair, reads the person from Forgejo's userinfo endpoint, writes a
`sessions` row and sets the session cookie. Logging out revokes the row; the
Forgejo login itself stays, and a person who wants to leave that too signs out
in Forgejo.

Signing in while a session already exists ends the old one first, so one
browser holds one session and one Forgejo token. A session that ends, however
it ends, has its two token columns emptied in the same statement that marks it
revoked; the row stays for the account page to show. Nothing deletes old rows
yet: that is a background job, and how background jobs run at all is open
question 7.

The id token is not validated and no key cache is kept: the identity is read
from userinfo over the same back channel the backend already trusts for
everything else it asks Forgejo.

Two cookies. `unicon_session` is the session: HttpOnly, SameSite=Lax, Path=/,
Secure when `UNICON_COOKIE_SECURE` is on. Its value is 32 random bytes; what
the database holds is their sha256, so a copy of the table is not a pile of
working cookies. `unicon_login` is short-lived and signed, and carries the
state, the PKCE verifier and where to land, so a login that is abandoned
leaves nothing behind.

The session row also holds that person's Forgejo tokens, encrypted with
`UNICON_TOKEN_ENCRYPTION_KEY`. A Forgejo OAuth token has no scopes, so whoever
holds one can do anything that person can do, including push: it is decrypted
only inside the service about to call Forgejo for them, is never returned by
an endpoint and is never logged. Any path that needs it refreshes first if the
access token dies within five minutes. The refresh happens with nothing locked
in the database: the row is read, the connection goes back to the pool, Forgejo
is called, and the new pair is written only if the stored one has not changed
meanwhile. Two tabs in one process queue behind a lock and produce one refresh;
two processes race and the loser takes the winner's pair.

Forgejo refusing a refresh is read carefully, because two different answers
arrive as `400`. `unauthorized_client` or `invalid_grant` means this person's
grant is over: the session is revoked and the answer is `401 forge_reauth`,
which the frontend turns into the session-expired modal. Anything else,
`invalid_client` above all, means Unicon's own OAuth registration is wrong; the
session is left alone and the answer is `502 forge_misconfigured`, because
signing everybody out one at a time would not fix a rotated client secret.

State-changing requests that carry the session cookie must have an `Origin`
(or a `Referer`) of this site, or they are refused with `origin_mismatch`.
With the frontend on the same origin as the API and SameSite=Lax on the
cookie, that is the whole CSRF story: no tokens, no hidden fields.

Deactivating and deleting an account are Forgejo operations, since there is no
users table: one flips Forgejo's `active` flag, the other deletes the account,
and both revoke every Unicon session first so a failed call leaves the person
signed out rather than half-deleted. Both need a login from the last few
minutes (`UNICON_REAUTH_WINDOW`), because a fresh trip through Forgejo is the
only proof of identity Unicon can ask for. Both refuse with `last_admin` while
the person is the only member of an admin team, and pass Forgejo's own message
through as `forge_rejected` when Forgejo is the one saying no, which is a
different answer from `forge_unreachable`.

## Three rules that are cheap now and expensive later

- **`api/` never imports `models/`, and services return schemas, not ORM
  objects.** A handler validates input, calls one service function and shapes
  a response. `domain/` imports nothing else in the package. `lint-imports`
  enforces all three; the contracts are at the bottom of `pyproject.toml`.
- **Within `/api/v1`, fields are added, never renamed or removed.** The
  frontend builds against a pinned copy of `openapi.json`, so a lagging pin
  stays correct exactly as long as this holds. A breaking change is `/api/v2`.
- **A person is a Forgejo numeric id, never a username.** Forgejo sends no
  event when someone renames, so a username is a cache, never a key. The same
  goes for organisations and repositories.

## Layout

```
unicon/
  main.py      the app factory        cli.py       api | migrate | openapi
  settings.py  every knob, read once at startup
  api/         routers: validate, call one service, shape the response
  auth/        cookies, PKCE and the encryption of the forge tokens
  schemas/     what the API returns, including the RFC 9457 problem document
  services/    use cases; the only place that writes to the database
  models/      the nine tables         db/          engine, session, migrations
  domain/      pure logic, imports nothing else
  forge/       the Forgejo clients: OIDC, admin, and a fake (Task 3 grows it)
  storage/     Garage (Task 6)
tests/
  unit/        no database              integration/ a real Postgres
```

## Licence

MIT. See `LICENSE`.
