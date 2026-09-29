# Unicon backend

The HTTP shell over the `forge` package: the routes, the role guard in front
of the organiser routes, the door the forge pushes events through, the
response schemas, the cookie names and flags, the Origin check, the request
log, the table from error to status code, and the OpenAPI document, started
by `unicon api`, and the operator's two commands beside it. It imports `forge.api`, the package's front door, and nothing else of it. It has
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

`uv sync` installs the `forge` package from the checkout beside this one,
`../forge`, so both repositories are cloned side by side; see
[Checks](#checks).

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
`POST /api/v1/auth/logout` ends this session and clears its cookie, and
`GET /api/v1/auth/register-url` answers where to make an account at the
forge, or null when sign-up there is closed.

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
session. That and `SameSite=Lax` are the whole CSRF story. One path is let
through: forge's `EVENTS_PATH` followed by an org's name, where the forge
pushes events with no browser behind them and the signature is what admits
the request.

`GET /api/v1/me` returns the caller's identity and their roles at every scope.
The session list (`GET /api/v1/me/sessions`), revoke
(`DELETE /api/v1/me/sessions/{session_id}`), sign-out-everywhere
(`DELETE /api/v1/me/sessions`), deactivate (`POST /api/v1/me/deactivate`)
and delete (`DELETE /api/v1/me`) routes each call the matching forge action
and return its refusal unchanged.

An action is one unit of work, and a route calls one per request. The action
opens its own transaction, commits before it returns and rolls back when it
raises, so by the time the route builds a 204 or a redirect the change is on
disk, and an action whose commit fails raises out of the call and is answered
as a 500. The session dependency, `CurrentSession`, reads the cookie and calls
`identity.current`. This shell never sees a transaction.

`GET /readyz` answers 503 `{"status": "not_ready"}` when forge says the
database did not answer; what failed is in forge's log and not in the
answer.

## Organisers

A scope has one URL shape: `/api/v1/orgs/{org}`, then
`/contests/{contest}`, then `/tasks/{task}`. Every organiser route is behind
one dependency, `require(role, at)` in `unicon/api/guard.py`: it reads the
session, builds the scope from the path parameters of the `at` prefix, and
calls `access.organiser` once, which reads the caller's roles, counts a role
held at a broader scope and a higher role, and either refuses with
`forbidden` or returns the `Organiser` the route hands to its action. The
action takes that value and reads no roles itself, so a request reads them
once. No route checks a role any other way.

Below, `<org>`, `<contest>` and `<task>` stand for the three prefixes,
`<scope>` for any of them and `<place>` for a contest or a task. The role is
the one the route needs at the scope in the third column.

| Route | Needs | At | Body | Answer |
|---|---|---|---|---|
| `POST /api/v1/orgs` | a session | | `name`, `description` | 202, the provisioning record |
| `GET <org>/provisioning` | the person who asked | | | the record, or 404 |
| `PATCH <org>` | admin | org | `description`, `display_name` | 204 |
| `POST <org>/contests` | manager | org | `name`, `title` | 202, the provisioning record |
| `GET <org>/contests` | observer | org | | the contests by name |
| `GET <contest>/provisioning` | observer | org | | the record, or 404 |
| `POST <contest>/tasks` | manager | contest | `name`, `title` | 202, the provisioning record |
| `GET <contest>/tasks` | observer | contest | | the tasks by name |
| `GET <task>/provisioning` | observer | contest | | the record, or 404 |
| `GET <task>` | observer | task | | the task's state |
| `GET <task>/publications` | observer | task | | the publications, oldest first |
| `GET <task>/release` | a session | | | whether the caller sees the task and may submit to it now, or 404 when the contest is hidden from them |
| `POST <task>/save` | manager | task | `changes`, `confirm`, `keep_as_draft`, `message` | the save's result |
| `GET <scope>/roles` | observer | scope | | the holders |
| `POST <scope>/roles` | manager | scope | `username`, `role` | 204 |
| `DELETE <scope>/roles/{user_id}` | manager | scope | | 204 |
| `GET <place>/tree?path=` | observer | place | | a folder's entries |
| `GET <place>/files/{path}?at=` | observer | place | | `path`, `encoding`, `content`, `token` |
| `GET <place>/history?path=` | observer | place | | every change, newest first |
| `PUT <place>/files/{path}` | manager | place | `encoding`, `content`, `token`, `message`, `confirm`, `keep_as_draft` | `version` at a contest, the save's result at a task |
| `POST <place>/files/{path}/rollback` | manager | place | `version`, `token`, `message`, `confirm`, `keep_as_draft` | as a write |

Creating an org answers at once with its `provisioning` record, and
forge's poller makes the org in the background; the status route follows
it to `ready` or to `failed`. The record is everything a follower needs:
`kind` (`org`, `contest` or `task`), `target`, `status`, `steps`, the steps
of its kind in the order they run, `last_step`, the last one completed,
`failed_step`, the step a failed record stopped at, `error`, the reason,
`retry_at`, when a failed record is next tried, `attempts` and `ready_at`.
`failed_step` and `retry_at` are null unless the status is `failed`, and
`failed_step` is null too when the work failed outside any step. An org's
description is at most 255 characters, the most the forge takes, on both
the create and the change. The person who asked
becomes the org's admin. Whether anyone signed in may ask is forge's
`UNICON_ORG_CREATION_OPEN`; with it off the route answers `forbidden`.

A contest's and a task's provisioning is followed at the scope above it,
since the thing being made holds no roles until it is there. Making a
contest needs the org to be there, and a task needs its contest.

The role routes are served under each of the three scope prefixes, and the
file routes under the contest and the task prefixes, each made by one
factory so each kind has its own operation names. A holder carries
`user_id`, `username`, `name`, `avatar_url`, `role`, the `scope` the role
is held at directly, and `inherited` when that is a broader scope than the
one asked about. Granting a different role than the one held moves the
person to it, which is how a person is promoted or demoted. Forge refuses a
manager granting admin or demoting or removing an admin (`forbidden`),
removing the last admin of a scope (`sole_admin`), and a role for a
contestant of that contest (`contestant_conflict`).

## Files and the save

A file's content travels as text: `encoding` is `utf-8` when its bytes are
UTF-8 and `base64` when they are not, so a binary file makes the same round
trip. A file comes with the `token` it was read with, and a write sends that
token back, or null to create the file; a token that has moved since is
answered `conflict` with nothing written. Forge checks every path, and one
that is empty, absolute, climbs out with `..` or holds a character a URL or
git reads as something else is `invalid_path` before the forge is asked. A
write to `contest.yaml` that does not validate is `invalid_definition`,
with each error at its YAML path, and a manager's change to one of its
admin-only keys is `admin_only`, naming each. A rollback writes the file as
it was at an older version back as a new change, so the history stays
whole.

A task is published by saving it. A write to a task's file, a rollback
there, and `POST <task>/save` are each a save, which `publications.save`
runs; the save route takes several files at once, each with its token. A save inside
`plans/` is `reserved_path`, and a manager's change to the task's name, its
`limits` or `statement.md` is `admin_only`. A save that checks publishes,
and one that does not is kept as a draft: its files are written, nothing is
published, and the last publication keeps grading. While the contest runs,
a save that changes how the task grades is `confirmation_required`, listing
what would change, and nothing is written. The same save with `confirm`
publishes; with `keep_as_draft` it is written as a draft that says what it
held back, and an empty save with `confirm` publishes that draft later.

A save answers with `outcome`. `published` carries the `publication`, its
`number`, `grading_changed`, the `changes`, and where the task's
`registration` for grading stands: `done`, `pending` or `not_needed`.
`draft` carries the `version` written, the `errors`, each `{path, message}`,
and what it `held_back`. `GET <task>` answers the version at the head, the
latest publication or none, whether the head is a draft, and the draft's
errors, worked out again on every read.

`GET <task>/release` is what a contestant is told, and needs only a session:
whether the task is `released`, `visible` and `open` to the caller now by
the server's clock, and the first reason it is `closed`. Nothing is released
before the task's first publication, and a task whose contest is hidden from
the caller is not found.

## The event door

`POST /api/v1/events/forge/{org}`, at forge's `EVENTS_PATH`, is where the
forge pushes an org's events, at the backend's internal URL inside the
stack. A body over 1 MiB is refused as `payload_too_large` before more of
it is read, whether its `Content-Length` says so or it runs past that with
no length, or with a length that is not a number. The route reads the raw body and the first of forge's
`SIGNATURE_HEADERS` the request carries, `X-Forgejo-Signature` and then
`X-Gitea-Signature`, and hands both to `events.check`; a wrong signature
and an org with no secret are both `forbidden`. A signed event is answered
204 and does nothing else. The public proxy answers this path with
404, so only the stack reaches it.

## Operator commands

Two things only the operator does are commands beside `unicon api`, run on
the stack with its `UNICON_*` settings. Neither is a route. Each starts
forge with no poller or timed pass beside it, so it does what it says and
nothing else.

```sh
unicon create-org acme --admin ada --description "Acme contests"
unicon create-account ada --email ada@example.org
```

`create-org` makes the org whatever `UNICON_ORG_CREATION_OPEN` says, with
the named user, who must already exist at the forge, as its first admin. It
runs the whole provisioning before it returns and prints the status and the
last step completed. It exits 0 when the org is ready and 2 when it stopped
at a step, which it names with the reason; the poller then tries it again
from there. A description over 255 characters is refused before forge is
called.
`create-account` makes a person's account at the forge for a deployment
with sign-up closed and prints the first password once; the person changes
it at their first sign-in. A refusal prints its reason and exits 1.

## Errors

Every error is an RFC 9457 problem document with a stable `code`. The
package's typed errors are mapped to a status in `unicon/api/errors.py` and
nowhere else:

| Code | Status |
|---|---|
| `not_found` | 404 |
| `forbidden`, `fresh_sign_in_required`, `origin_mismatch`, `admin_only`, `reserved_path` | 403 |
| `conflict`, `sole_admin`, `contestant_conflict`, `shared_workflow_owner`, `confirmation_required` | 409 |
| `payload_too_large` | 413 |
| `rejected`, `invalid_name`, `invalid_definition`, `invalid_path`, `validation_error` | 422 |
| `unauthenticated`, `session_expired` | 401, and the session cookie is cleared |
| `sign_in_invalid`, `sign_in_denied` | 400 |
| `forge_misconfigured` | 502 |
| `forge_unavailable` | 503 |

`sole_admin` carries `scopes`, each `{"kind", "name"}`,
`contestant_conflict` carries `contests`, `shared_workflow_owner` carries
`workflows`, `admin_only` carries `keys`, `reserved_path` carries `paths`,
`confirmation_required` carries `changes`, `invalid_definition` carries
`errors`, each `{"path", "message"}`, and `invalid_path` carries `path`, so
the browser can show what stands in the way. A refusal
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
skipped without it. Provisioning moves along with the kit's `tick`, one tick
of the poller the app's lifespan would run, and a contestant is made with
its `register_contestant`. The openapi diff fails when a response changed and nobody
regenerated the document.

The `forge` package is the checkout beside this one: `[tool.uv.sources]`
names `../forge`, installed editable, and `dependencies` names
`unicon-forge` with no version, so a change there, its code and the
migrations `unicon-forge migrate` applies, is live here at once. Every step
above but `docker build .` runs with that folder beside this one. CI checks
out this repository alone and the image is built from this repository
alone, so there `uv sync --frozen` and `docker build .` fail while the
source is the checkout. A forge release is followed here by one edit and
`uv lock`: `[tool.uv.sources]` names the release's wheel, `dependencies`
pins its version, and the lock holds the wheel's hash. From then a change in
that repository reaches this one only when someone moves the pin the same
way, and CI and the image build have all they need in this repository.

## Layout

```
unicon/
  main.py      the app factory; forge starts and stops with the app
  cli.py       api | openapi | create-org | create-account
  api/         routes, the session dependency, the role guard, cookie names and
               flags, the error mapping and the middleware
  schemas/     what the API answers with, including the problem document
tests/
  unit/        no database
  integration/ a real Postgres and the in-memory forge, through the browser's hops
```

## Licence

MIT. See `LICENSE`.
