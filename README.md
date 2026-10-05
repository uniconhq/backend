# Unicon backend

The HTTP shell over the `forge` package: the routes, the role guard in front
of the organiser routes, the doors the forge and a grading run call, the
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
cp .env.example .env          # then fill it in
set -a; . ./.env; set +a
uv run unicon-forge migrate   # the forge package's command, installed with it
uv run unicon api             # http://localhost:8000
```

`GET /openapi.json` is the document the frontend generates from, served on
the backend's own port only: the proxy answers it 404, and the frontend reads
the copy committed here. The Swagger and ReDoc pages are off, since an API
browser is not part of what a deployment exposes. `GET /healthz` says the process is up. `GET /readyz` says the database
answered. `GET /api/v1/time` is the server clock, the only clock the frontend
trusts. With `UNICON_FORGE=fake` the whole shell runs against the in-memory
forge, with no git host at all.

The database is migrated by the forge package, not by this shell: the
package installs `unicon-forge`, and `unicon-forge migrate` reads
`UNICON_DATABASE_URL`, applies the migrations and exits. The stack runs it
from this image before the API starts.

The real configuration comes from the compose stack in `deploy`, whose
bootstrap writes a `.env` with the secrets and the operator's choices, and
whose `compose.yaml` hands this image its `UNICON_*` variables, the database
URL and the other services' addresses written there. Every one of them is
read by forge, `UNICON_SESSION_SIGNING_KEY` included; this shell reads none.
`unicon api` calls `forge.api.log.setup()` first, before the server starts, so every line is JSON, and the app's
lifespan calls `forge.api.start(callback_path="/api/v1/auth/callback")`,
giving forge the one thing it cannot know, this shell's callback route. A
missing or malformed variable stops the process at start with the variable
named. `unicon openapi` builds the app without starting forge, so it reads no
setting; the Origin check asks forge for the public URL on the first request
it checks. Two hostnames there are the stack's: `postgres` in
`UNICON_DATABASE_URL` and `forgejo` in `UNICON_FORGE_INTERNAL_URL`; from a
laptop shell use addresses it reaches, as `.env.example` does.

## Sign-in and sessions

Sign-in is the forge's OpenID Connect. `GET /api/v1/auth/login` asks the
package for the redirect, keeps what checks the answer in the signed
short-lived `unicon_sign_in` cookie, and sends the browser to the forge.
`/callback` hands the code, the cookie's contents and the session the browser
already had to `sign_in.complete`, which creates the new session and ends the
old one in one transaction; the route sets the `unicon_session` cookie and
lands on the `next` path forge validated when the sign-in started. A callback with no sign-in cookie, or a state that does
not match, lands on `/login` with the error's code in the query.
`POST /api/v1/auth/logout` ends this session and clears its cookie,
`GET /api/v1/auth/register-url` answers where to make an account at the
forge, or null when forge's `UNICON_FORGE_REGISTRATION_OPEN` says sign-up
there is closed, and `GET /api/v1/auth/forge-url` answers where a browser
reaches the forge's own pages, where the account's password, email and
two-factor are changed. Neither of the last two needs a session.

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
session. That and `SameSite=Lax` are the whole CSRF story. Three doors a
machine calls with no browser behind it are let through, each admitted by
what it carries rather than where it came from: forge's `EVENTS_PATH`
followed by an org's key, where the forge pushes events under a signature;
the CI's configuration extension at forge's `CI_CONFIG_PATH`, under the
CI's signature; and a grading run's callback at `CALLBACK_PATH` with one
grading's id, under the run's token.

`GET /api/v1/me` returns the caller's identity as `user` and their `roles`
at every scope, each with the `names` of where it is held.
The session list (`GET /api/v1/me/sessions`), revoke
(`DELETE /api/v1/me/sessions/{session_id}`), sign-out-everywhere
(`DELETE /api/v1/me/sessions`), deactivate (`POST /api/v1/me/deactivate`)
and delete (`DELETE /api/v1/me`) routes each call the matching forge action
and return its refusal unchanged.

A route returns the record its forge action gives and names the model it
answers with as its `response_model`, and FastAPI reads each field off the
record by name and sends only the fields that model lists. Where everything
a forge record holds may go to the browser, the forge's own type is the
model, as for a task's release, a folder's entries, the history and a
published save. Everywhere else a model in `unicon/schemas` lists the fields
that go out, which leaves behind the keys the forge's ids are built from,
another person's email (but for the address an organiser typed into an
invite, which the scope's organisers see), the address a session came from, the forge's ids
for a publication's workflows, and where a run put its log. Field names are
the forge's: a contest is `where` it is, by its `org` and `contest` names,
and its `name` is its title. An answer is sent whole, so
`unicon/api/openapi.py` marks every field of an answer's schema required in
the document, a field with a default included.

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
`/contests/{contest}`, then `/tasks/{task}`. The names in it are labels:
forge files every org, contest and task under a key that never changes, and
turns the names into those keys. Every organiser route is behind one
dependency, `require(role, at)` in `unicon/api/guard.py`: it reads the
session and the path parameters of the `at` prefix and calls
`access.organiser_at` once, which finds the scope by those names, reads the
caller's roles, counts a role held at a broader scope and a higher role, and
either refuses with `forbidden` or returns the `Organiser` the route hands
to its action. A name in the path that is not there is `forbidden` too,
unless the caller holds the role above it, when it is `not_found`, so no
route tells anyone else which contests or tasks exist. The action takes that
value and reads no roles itself, so a request reads them once. No route
checks a role any other way. Every answer that shows a name takes it from
the record forge returns, never from an id.

Below, `<org>`, `<contest>` and `<task>` stand for the three prefixes,
`<scope>` for any of them and `<place>` for a contest or a task. The role is
the one the route needs at the scope in the third column.

| Route | Needs | At | Body | Answer |
|---|---|---|---|---|
| `POST /api/v1/orgs` | a session | | `name`, `description` | 201, the org's `name` |
| `PATCH <org>` | admin | org | `description`, `display_name` | 204 |
| `POST <org>/contests` | manager | org | `name`, `title` | 201, the contest's `name` |
| `GET <org>/contests` | observer | org | | the contests by name |
| `POST <contest>/tasks` | manager | contest | `name`, `title` | 201, the task's `name` |
| `GET <contest>/tasks` | observer | contest | | the tasks by name |
| `GET <task>` | observer | task | | the task's state |
| `GET <task>/publications` | observer | task | | the publications, oldest first |
| `GET <task>/release` | a session | | | whether the caller sees the task and may submit to it now, or 404 when the contest is hidden from them |
| `GET <contest>/contestants` | observer | contest | | every registration, oldest first |
| `POST <contest>/contestants/{user_id}/approve` | manager | contest | | the registration |
| `POST <contest>/contestants/{user_id}/reject` | manager | contest | `reason` | the registration |
| `POST <contest>/contestants/{user_id}/reopen` | manager | contest | | the registration, pending again |
| `POST <contest>/contestants/{user_id}/remove` | manager | contest | | the registration |
| `PUT <contest>/contestants/{user_id}/extension` | manager | contest | `seconds` | the registration |
| `GET <contest>/organise/teams` | observer | contest | | every team, with its members and the people asking or asked in |
| `POST <contest>/organise/teams` | manager | contest | `name`, `leader` | 201, the team |
| `DELETE <contest>/organise/teams/{team_id}` | manager | contest | | 204 |
| `POST <contest>/organise/teams/{team_id}/members` | manager | contest | `user_id` | the team, the person moved in from any other |
| `DELETE <contest>/organise/teams/{team_id}/members/{user_id}` | manager | contest | | the team |
| `PUT <contest>/organise/teams/{team_id}/leader` | manager | contest | `user_id` | the team |
| `POST <task>/save` | manager | task | `changes`, `confirm`, `keep_as_draft`, `message` | the save's result |
| `GET <scope>/roles` | observer | scope | | the holders |
| `POST <scope>/roles` | manager | scope | `username`, `role` | 204 |
| `DELETE <scope>/roles/{user_id}` | manager | scope | | 204 |
| `GET <scope>/invites` | observer | scope | | the scope's invites, newest first |
| `POST <scope>/invites` | manager | scope | `grants`, `username` or `email`, `days` | 201, the invite |
| `POST <scope>/invites/{invite_id}/send-again` | manager | scope | | the invite, mailed again with a new link |
| `POST <scope>/invites/{invite_id}/withdraw` | manager | scope | | the invite, `withdrawn` |
| `GET <place>/tree?path=` | observer | place | | a folder's entries |
| `GET <place>/files/{path}?at=` | observer | place | | `path`, `encoding`, `content`, `token` |
| `GET <place>/history?path=` | observer | place | | every change, newest first |
| `PUT <place>/files/{path}` | manager | place | `encoding`, `content`, `token`, `message`, `confirm`, `keep_as_draft` | `version` at a contest, the save's result at a task |
| `POST <place>/files/{path}/rollback` | manager | place | `version`, `token`, `message`, `confirm`, `keep_as_draft` | as a write |
| `GET <task>/gradings?limit=` | observer | task | | the task's gradings, newest first, each with why it failed |
| `POST <task>/gradings/{grading}/cancel` | manager | task | | the grading, `cancelled` |
| `POST <task>/gradings/{grading}/retry` | manager | task | | the new attempt, `queued` |
| `POST <task>/rejudge` | manager | task | | what the rejudge did |
| `GET <place>/announcements` | observer | place | | every announcement, closed ones included, oldest first |
| `POST <place>/announcements` | manager | place | `title`, `body` | 201, the announcement |
| `PATCH <place>/announcements/{number}` | manager | place | `title`, `body` | the announcement |
| `POST <place>/announcements/{number}/close` | manager | place | | the announcement, `closed` |
| `GET <org>/clarifications` | a role anywhere in the org | | | every question still open across the org, oldest first |
| `GET <contest>/clarifications` | observer | contest | | every question of the contest, answered ones included |
| `POST <contest>/clarifications/{asker}/{number}/replies` | manager | contest | `body` | the question, still open |
| `PUT <contest>/clarifications/{asker}/{number}/answered` | manager | contest | | the question, answered and closed |
| `DELETE <contest>/clarifications/{asker}/{number}/answered` | manager | contest | | the question, open again |
| `POST <contest>/clarifications/{asker}/{number}/announcement` | manager | contest | `title`, `body` | 201, the announcement it made |

Creating an org, a contest or a task makes the whole thing at the forge
and the CI before the route answers, and the answer is the new thing's
`name`. A step that fails is refused with its reason, and asking again is
safe. An org's description is at most 255 characters, the most the forge
takes, on both the create and the change. The person who asked becomes the
org's admin. Whether anyone signed in may ask is forge's
`UNICON_ORG_CREATION_OPEN`; with it off the route answers `forbidden`.
Making a contest needs the org to be there, and a task needs its contest.

The role routes are served under each of the three scope prefixes, and the
file routes under the contest and the task prefixes, each made by one
factory so each kind has its own operation names. A holder carries the
`user`, by `id`, `username`, `name` and `avatar_url`, the `role`, and
`at_names`, the names of the scope the role is held at directly: the one
asked about, or a broader one. Granting a different role than the one held moves the
person to it, which is how a person is promoted or demoted. Forge refuses a
manager granting admin or demoting or removing an admin (`forbidden`),
removing the last admin of a scope (`sole_admin`), and a role for a
contestant of that contest (`contestant_conflict`).

The invite routes are served under each of the three scope prefixes too. An
invite names a `username` or an `email`, and `grants` one of the three
roles at the scope or, at a contest, a `contestant`'s place; it stands for
`days`, 14 unless given and at most 90. It carries `where`, the scope's
names, `invited_by`, its `status` (`pending`, `accepted`, `declined` or
`withdrawn`), `expired` for a pending one past `expires_at`, and
`mail_status`: `waiting` until the mail server takes it, `sent`, `failed`,
or `off` on a deployment with no mail server. The mail goes out after the
route answers, so a mail server that is down never fails the click. Forge
refuses a manager inviting an admin (`forbidden`), a contestant's place
anywhere but a contest, a target that is both or neither, and someone who
holds it already or could not take it (`invalid_invite`), the same pending
invite twice (`already_invited`), and an org's thousand-and-first invite of
a day (`invite_limit`). Sending again makes a new link, so the old one
stops working, and gives the invite its whole lifetime again, a lapsed one
included; it is refused within ten minutes of the last mail
(`invite_limit`) and where the deployment sends no mail (`invalid_invite`).
Withdrawing takes back a pending invite, or an accepted contestant's place
until its person registers; anything else is `wrong_status`. A list shows
at most 500. A username whose account has no confirmed address gets no
mail, and its invite reads `failed`.

A contestant of a contest with teams works with a session alone, and forge
checks they are its approved contestant and, for the leader's routes, that
they lead the team named: `GET <contest>/my-team` gives their team and the
teams they asked or are asked into; `GET <contest>/teams` lists the teams
with their size and the contest's `max_size`; `POST <contest>/teams` with a
`name` makes one they lead; `POST <contest>/teams/{team_id}/request` asks to
join, or accepts the leader's invitation, and `/cancel` takes that back;
`POST <contest>/my-team/leave` leaves; and the leader's
`POST <contest>/teams/{team_id}/invite` with a `username`,
`POST .../members/{user_id}/approve` and `DELETE .../members/{user_id}` ask
someone in, let a request in, and take someone out or turn a request down.
Once in a team, the person's submissions, limits and questions are the
team's, and a question on a team's desk is named `team.<id>` where a
person's is named by their user id. Refusals: `teams_off`,
`invalid_team_name`, `team_name_taken`, `team_full` (with `limit`),
`in_team`, `submitted_alone`, `team_has_submissions` and `team_changed`.

The person an invite is for acts on it with a session alone:
`GET /api/v1/me/invites` lists their pending invites, lapsed ones flagged,
including any sent to an address the forge has confirmed is theirs;
`POST /api/v1/me/invites/open` with the `token` after the `#` of the mail's
link opens one, in the body so the token never sits in a URL;
`POST /api/v1/me/invites/{invite_id}/accept` takes what it grants and
`/decline` grants nothing, and either on a decided invite is
`wrong_status`. Anyone else's invite is `not_found`, a lapsed one is
`invite_expired` (410), and a link opened while the forge cannot say whose
address it is answers `forge_unavailable`. Accepting a contestant's place lets
the person register for an invite-only contest and see a hidden one.

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
publishes. A save with `keep_as_draft` is written as a draft that says what
it held back and publishes nothing, on any save, and an empty save with
`confirm` publishes that draft later.

A save answers with what it published or with the draft it kept. A
publication carries the `publication`, its `number`, `grading_changed` and
the `changes`; a draft carries the `version` written, the `errors`, each
`{path, message}`, and what it `held_back`. `GET <task>` answers the version at the head, the
latest publication or none, whether the head is a draft, and the draft's
errors, worked out again on every read.

`GET <task>/release` is what a contestant is told, and needs only a session:
whether the task is `released`, `visible` and `open` to the caller now by
the server's clock, and the first reason it is `closed`. Nothing is released
before the task's first publication, and a task whose contest is hidden from
the caller is not found.

## Contestants and visitors

A contestant's routes need a session and no role, since the person holds none
in the contest they enter:

| Route | Body | Answer |
|---|---|---|
| `GET /api/v1/contests` | | every published contest the caller may enter or has entered, newest start first, with their own `status` |
| `POST <contest>/registration` | `invite_code` | 201, the caller's registration |
| `GET <contest>/registration` | | the caller's registration, or null |
| `GET <contest>/home` | | the contest's home for the caller |
| `GET <task>/page` | | a released task's statement and limits |
| `GET <contest>/home/announcements` | | the open announcements of the contest and of each task released to the caller |
| `GET <task>/page/announcements` | | the open announcements of a released task |
| `POST <contest>/questions` | `title`, `body`, `task` | 201, the question, asked privately |
| `GET <contest>/questions` | | the caller's own questions, with every message |
| `POST <contest>/questions/{number}/comments` | `body` | the question, opened again when it was answered |
| `GET /api/v1/live` | | the session's live updates, as Server-Sent Events |

Registering answers pending, or approved when the contest approves on its
own. A registration the contest's rules refuse answers with the rule's code:
`registration_closed`, `is_staff`, `invite_required`, `wrong_invite_code` and
`domain_not_allowed` as 403, `already_registered` and `contest_full` as 409.
A registration carries its `status`, the `reason` when it was rejected, its
times, and the `time_extension` in seconds. The home carries the contest
`where` it is, its title as `name`, its dates and `state`, the caller's
`registration`, whether the caller `organises` the contest and so may not
enter it, whether the window is `registration_open` and whether registering
is `invite_only` or `asks_code`, the caller's own `deadline`, which is the
end plus their extension, `now`, the server's clock when it was read, and
the `tasks` released to them, each with its `name`, `label`, `title`,
`points` and `release`. A task's page carries its `statement` in Markdown
and its `limits`: `submissions`, at most `rate.count` in any `rate.per`
seconds, and `max_size` in bytes.
For a contest the caller may not see, the home answers 404, the same as for
one that is not there, and so does the page of a task that is not visible to
them; the caller's own registration reads null wherever they have none.

The organiser's contestants routes are in the table above, and answer with
the same registration and the person's `user_id` and `user`, which carries
their `id`, `username`, `name`, `email` and `avatar_url` and is null once
the account is gone. A decision the registration's status does not allow
is `wrong_status`, carrying the status as `current`; a rejection needs a `reason` (`invalid_reason`), and an
extension is between none and a year (`invalid_extension`), and one
of more than a billion seconds either way is not taken at all
(`validation_error`). Reopening takes a rejection back: the registration is
pending again with its reason cleared, and since it takes a place again it
is refused with `contest_full` when none is free and `is_staff` when the
person holds a role at the contest by now.

A visitor with no session calls the routes under `/api/v1/public`, which
read no cookie: `GET /api/v1/public/contests`, every contest whose
`visibility` is `public` and that is published; `GET
/api/v1/public/contests/{org}/{contest}`, one of them with its released
tasks; and `GET /api/v1/public/contests/{org}/{contest}/tasks/{task}`, a
released task's statement. Anything else answers 404 there. Every
contestant's and organiser's route answers a request with no session 401;
the few others that need none are the sign-in's own, the server's clock, the
health checks and the machines' doors, and a test lists them all.

## Uploads and submissions

A contestant submits to a task they are an approved contestant of, while it
is open to them, and reads back only their own submissions. Each route needs
a session and no role; `<task>` is the task's prefix.

| Route | Body | Answer |
|---|---|---|
| `POST <task>/uploads` | `input`, `filename`, `size`, `sha256`, `content_type` | 201, a slot |
| `POST <task>/uploads/{upload}/complete` | | the upload |
| `POST <task>/submissions` | `idempotency_key`, `inputs` | 201, the submission |
| `GET <task>/submissions` | | the caller's own, newest first |
| `GET <task>/submissions/{number}` | | one of them |
| `GET <task>/submissions/{number}/files` | | what it was made with |
| `GET <task>/submissions/{number}/log?stage=` | | its run log, as plain text |

A file never passes through this process. The browser asks for a slot for
one file of a contestant input, declaring its `size` and `sha256`, and the
slot's `url` is the proxy's upload door, `/-/uploads/<id>`, good until
`expires_at`; a slot that is `ready` is for a file the forge holds already,
and nothing is sent. The browser PUTs the file there, and the proxy, having
asked this process whether that upload may start (`unicon/api/door.py`),
puts the body through to the forge's large-file store, which hashes what
arrives. The browser then completes the upload, and forge asks the store
whether it holds the file: an upload carries its `status`, `verified` once
it does, with its `size` and `sha256`. Completing again answers the same. An upload is its owner's alone, for one task, and anyone
else's is not found.

A submit names, for each of the task's contestant inputs by id, the
`uploads` of its files and the `language` of a code input, or the `value` of
a text, number or true-or-false input, with an `idempotency_key` the browser
makes once per submit, 8 to 128 letters, digits, `-` and `_`. The same key
sent again answers with the submission it made and makes nothing. A
submission carries its `number`, `submitted_at` and `gradings`, the latest
attempt at each of the task's stages, each with its `id`, `stage`,
`attempt`, `status`, the stage's `show`, and of the verdict what `show`
lets the contestant see: `full` the `outcome`, `metrics`, `summary`,
`tests` and whether there is a `log`, `metrics` the outcome and metrics,
`hidden` the status alone. An outcome is one of the runner's list, metrics
are named numbers, and a test's row is its `id`, `outcome`, `time_ms`,
`memory_kb`, each null when not measured, its own `metrics` and the
checker's `message` or null. What is not shown is null; the route renders
what forge gives it and nothing more. The files route answers each input's
`files`, by their paths in the submission, its `language` or its `value`.
A file itself is downloaded through the proxy's download door,
`/-/downloads/<org>/<contest>/<task>/<number>/<path>`, which asks this
process whether the caller may read it and then streams it from the forge
as an attachment named after the file, so a file of any size passes
through the proxy and never through this process. Another contestant's submission is not found, the same as one
that is not there, and a number that cannot be one is `validation_error`.

A slot or a submit the task's rules refuse answers with the rule's code:
`task_closed`, with its `reason`, `ended` or `submissions_closed`,
`archived` and `not_approved` as 403; `submission_limit` with its `limit`,
`upload_not_ready` with the `uploads` refused, and `upload_limit`, too many
open uploads, with its `limit` and `bytes`, as 409; `rate_limited` as 429 with the `rate` and
`retry_at`, which the `Retry-After` header carries too; `too_large` as 413
with the `limit` in bytes and the `input` whose limit it is, or null for the
task's; `upload_not_yours` as 404 with the `uploads`; and `invalid_inputs`,
each of its `errors` naming its `input`, and `invalid_idempotency_key` as
422.


## Workflows

`POST /api/v1/workflows` makes a workflow and needs a session and no role.
The body names its `owner` and `name`; the owner is the caller's own
username, or the name of an org where they hold the manager role or above,
and forge decides which. The answer is 201 with the workflow's `owner` and
`name`, never its id at the forge, which is built from an org's key. The
workflow is private, and its first commit, a `workflow.yaml` named
`<owner>/<name>` with the steps of `unicon/classic@v1`, is the caller's. An
observer of the org, a person with no role there, an org that is not there
and another person's username are all `forbidden`, in the same words, so the
answer tells nobody which orgs exist. A name that breaks the rules, or a
username that cannot name a workflow, is `invalid_name`, and a name the
owner has already is `conflict`.

## The event door

`POST /api/v1/events/forge/{org}`, at forge's `EVENTS_PATH`, with the org's
key where `{org}` stands, is where the forge pushes an org's events, at the backend's internal URL inside the
stack. A body over 1 MiB is refused as `payload_too_large` before more of
it is read, whether its `Content-Length` says so or it runs past that with
no length, or with a length that is not a number. The route reads the raw body and the first of forge's
`SIGNATURE_HEADERS` the request carries, `X-Forgejo-Signature` and then
`X-Gitea-Signature`, and hands both to `events.check`; a wrong signature
and an org with no secret are both `forbidden`. A signed event is answered
204 at once, and only then is the same body, untouched, handed with its kind
from `X-Forgejo-Event` or `X-Gitea-Event` to `events.publish`, which tells
the live streams what thread it changed; the forge never waits on that. A
failure there comes after the answer, so it is logged as
`events.publish_failed`.
The public proxy answers this path with 404, so only the stack reaches it.

## Announcements, questions and live updates

An organiser's announcement routes are served under the contest and the
task prefixes, made by one factory, like the file routes; there is no
delete, and a closed announcement stays readable. An announcement carries
`where` it is by name, its `number` there, `title`, `body`, `posted_at`,
`closed`, whether it `answers_question`, and, to an organiser, `answers`,
the question by its asker's user id and number. A question is named by its
asker's user id and its number among their questions in the contest, and
carries its contest by name, the `asker`, `number`, the `task` it names,
`title`, `body`, `asked_at`, `answered`, `closed` and every message, each
saying whether the asker wrote it. Asking needs an approved contestant
(`not_approved` otherwise), and an empty or too long title or text is
`invalid_message`, naming the `field`.

`GET /api/v1/live` holds one Server-Sent Events stream per open tab: each
event is named by its kind, `grading`, `announcement`, `clarification` or
`resync`, and its data is one id, never what changed, so a page asks for the
thing again through the routes above. A comment every fifteen seconds keeps
the connection open and tells the server a browser has gone. The route
answers only once forge has checked the session and subscribed, so a
refusal is an ordinary error. The stream ends when the session does, or
when the same session opens more than eight, which ends the oldest, and
the browser reconnects after five seconds. The server waits at most five
seconds for open streams when it shuts down.
It is sent with `X-Accel-Buffering: no`, and the proxy serves the path with
buffering off.

## The grading run's doors

A grading run calls three routes with no session, and each hands forge the
request as it arrived, since what admits it is over its exact bytes; a body
is read raw and only up to a bound, refused past it as `payload_too_large`
the way the event door refuses one.

`POST /api/v1/ci/config`, forge's `CI_CONFIG_PATH`, is the CI's
configuration extension, called from inside the stack; the public proxy
answers it with 404. Its method, its target, the path undecoded and the
query exactly as sent, every header and the body, at most 1 MiB, go to
`runs.config` as a `CiRequest`, which checks the CI's signature over them
and answers the run's steps; the route answers those bytes in the media
type forge gives. A request that does not verify, names no grading, or
names one not being started with its variables is `ci_request_refused`,
never an empty answer.

`GET /api/v1/gradings/{grading}/envelope?key=` serves the envelope the
harness fetches as the run begins, for the envelope key the URL carries,
once, while the grading is dispatched; a wrong key is `not_found`, and a
second fetch, a grading the CI holds no run of, or one whose deadline has
passed, `grading_closed`. It carries the run's callback token,
so it is answered `Cache-Control: no-store`.

`POST /api/v1/gradings/{grading}/callback` takes a run's report, `started`,
`progress` or `finished` with the verdict, at most 4 MiB, handing the
`Authorization` header and the raw body to `runs.callback`, and answers the
grading's `status` after it. A missing or wrong bearer token is
`invalid_token`, a body that is no report `invalid_callback`, and a grading
that takes no reports now `grading_closed`. The same verdict sent again is
answered the same. `grading_closed` is a 410: a grading that has finished,
or whose run has ended, never takes an envelope or a report again.
`invalid_callback` is a 422
like every other body that does not fit. The harness stops reporting at a
401, 403, 404, 409 or 410 and sends a verdict again only after a 5xx or a
429, so each of these refusals ends a run's reporting and none is retried.
The request log never records the query or a header, so neither the key nor
the token reaches it.

An organiser managing a task cancels one of its gradings, retries a
finished one as a new attempt, or rejudges the whole task against its
current publication, with the three routes in the organisers' table. A
grading is named under its task's prefix, where the guard checks the role,
and a grading of any other task is not found there, the same as one that is
not there at all, whatever the caller may do at that other task; forge
checks the role again at the grading's own task. A grading carries its
`id`, the `submission_number` and `submitted_at`, the `publication`,
`stage`, `attempt`, `status`, `error`, `verdict`, whether there is a `log`,
`progress` (the `step` last reported and how many of its containers are
`done` of the `total`) and its times; cancelling a finished one or retrying
one that is not finished is `wrong_status` with its `current` status, and
retrying one with another attempt still being graded is `conflict`. A rejudge answers the
`publication` it grades against and how many attempts it `queued`,
`cancelled` first, `left_running` and `passed_over`.

A contestant reads the run log of their own submission's latest attempt at
a `stage`, or at the first stage with one, only where that stage's `show` is
`full`; anywhere else it is `not_found`, and one larger than forge serves is
`log_too_large`. It is answered as plain text with the download's headers.

## Operator commands

Two things only the operator does are commands beside `unicon api`, run on
the stack with its `UNICON_*` settings. Neither is a route.

```sh
unicon create-org acme --admin ada --description "Acme contests"
unicon create-account ada --email ada@example.org
```

`create-org` makes the org whatever `UNICON_ORG_CREATION_OPEN` says, with
the named user, who must already exist at the forge, as its first admin. It
makes the whole org before it returns, and exits 0 once it is made. A step
that fails is a refusal, printed with its reason, and running the command
again is safe. A description over 255 characters is refused before forge is
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
| `not_found`, `upload_not_yours` | 404 |
| `forbidden`, `ci_request_refused`, `fresh_sign_in_required`, `origin_mismatch`, `admin_only`, `reserved_path`, `registration_closed`, `is_staff`, `invite_required`, `wrong_invite_code`, `domain_not_allowed`, `task_closed`, `archived`, `not_approved` | 403 |
| `conflict`, `sole_admin`, `contestant_conflict`, `shared_workflow_owner`, `confirmation_required`, `already_registered`, `contest_full`, `already_invited`, `teams_off`, `team_name_taken`, `team_full`, `in_team`, `submitted_alone`, `team_has_submissions`, `team_changed`, `wrong_status`, `submission_limit`, `upload_not_ready`, `upload_limit`, `log_too_large` | 409 |
| `grading_closed`, `invite_expired` | 410 |
| `payload_too_large`, `too_large` | 413 |
| `rate_limited`, `invite_limit` | 429, with `Retry-After` |
| `rejected`, `invalid_name`, `invalid_definition`, `invalid_path`, `invalid_reason`, `invalid_extension`, `invalid_invite`, `invalid_team_name`, `invalid_inputs`, `invalid_idempotency_key`, `invalid_callback`, `invalid_message`, `validation_error` | 422 |
| `unauthenticated`, `session_expired` | 401, and the session cookie is cleared |
| `invalid_token` | 401 |
| `sign_in_invalid`, `sign_in_denied` | 400 |
| `forge_misconfigured` | 502 |
| `forge_unavailable` | 503 |

`sole_admin` carries `scopes`, each `{"kind", "name"}`,
`contestant_conflict` carries `contests`, `shared_workflow_owner` carries
`workflows`, `admin_only` carries `keys`, `reserved_path` carries `paths`,
`confirmation_required` carries `changes`, `already_invited` carries `invite`, the one held already, `invalid_definition` carries
`errors`, each `{"path", "message"}`, `invalid_path` carries `path`,
`wrong_status` carries `current`, and the refusals of an upload or a submit
carry what the section above names, so the browser can show what stands in
the way. A member named like a field of the document itself, such as `status`,
would replace it, so it is left out and logged as `errors.member_clash`. A refusal
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
skipped without it. A contestant is made with the kit's
`register_contestant`. The openapi diff fails when a response changed and nobody
regenerated the document.

The `forge` package comes from one release, named in `[tool.uv.sources]`
and locked to the wheel's hash in `uv.lock`, so a change in that repository
reaches this one only when someone moves the pin. Moving it is one edit
followed by `uv lock`, and it carries both the code and the migrations
`unicon-forge migrate` applies. While a forge change this repository needs is
not released yet, the source is the sibling checkout at `../forge` instead,
editable. The image then builds with that checkout handed in as the named
context `forge`, `docker build --build-context forge=../forge .`, which the
dev stack in `deploy` does; `docker build .` alone builds only once the pin
names the release again, which is what this repository's CI builds.

## Layout

```
unicon/
  main.py      the app factory; forge starts and stops with the app
  cli.py       api | openapi | create-org | create-account
  api/         routes, the session dependency, the role guard, cookie names and
               flags, the error mapping and the middleware
  schemas/     the request bodies, the models answers go out as where they
               hold less than the forge's record, and the problem document
tests/
  unit/        no database
  integration/ a real Postgres and the in-memory forge, through the browser's hops
```

## Licence

MIT. See `LICENSE`.
