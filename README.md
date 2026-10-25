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
session. That and `SameSite=Lax` are the whole CSRF story. Four kinds of
door a machine calls with no browser behind it are let through, each
admitted by what it carries rather than where it came from: forge's
`EVENTS_PATH` followed by an org's key, where the forge pushes events
under a signature; the CI's configuration extension at forge's
`CI_CONFIG_PATH`, under the CI's signature; a grading run's callback at
`CALLBACK_PATH` with one grading's id, under the run's token; and a run
task's step's report, upload list and done, at `STEP_PATH`,
`UPLOADS_PATH` and `DONE_PATH` with one grading's id and one step's name,
under the step's token.

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
value and reads no roles itself, so a request reads them once. A few reads
are open to anyone holding any role at a scope or at anything in it, and the
action narrows what each reads: their dependency, `anywhere(at)`, asks as
`require(Role.OBSERVER, at)` does first, so an observer there costs the
same one read, and for someone holding roles only further in reads them
twice more, once to find one and once to check it, handing the route the
`Organiser` at that narrower scope; a forge that does not answer the read
that finds one is `forge_unavailable`. Holding none there, or naming a
scope that is not there, is `forbidden`, "This needs a role at `<address>`
or at anything in it." Every other route checks a role this way, but one:
`GET <org>/clarifications` takes a session alone, and forge reads the
person's roles and gives the questions of the contests they observe, none
for a role only at a task. Every answer that shows a name takes it from
the record forge returns, never from an id.

Below, `<org>`, `<contest>` and `<task>` stand for the three prefixes,
`<scope>` for any of them and `<place>` for a contest or a task. The role is
the one the route needs at the scope in the third column.

| Route | Needs | At | Body | Answer |
|---|---|---|---|---|
| `POST /api/v1/orgs` | a session | | `name`, `description` | 201, the org's `name` |
| `GET <org>` | a role at the org or in it | org | | the org's `display_name` and `description` |
| `PATCH <org>` | admin | org | `description`, `display_name` | 204 |
| `POST <org>/contests` | manager | org | `name`, `title` | 201, the contest's `name` |
| `GET <org>/contests` | observer | org | | each contest's `name`, `state`, `start` and `end`, the last three null when its settings do not read |
| `POST <contest>/tasks` | manager | contest | `name`, `title` | 201, the task's `name` |
| `GET <contest>/tasks` | observer | contest | | the tasks by name |
| `GET <contest>/organise/tasks` | observer | contest | | the tasks the contest lists, in its order, each with its letter, state and timeline, whether it is withdrawn, its submissions and what taking it out would do |
| `POST <task>/take-out` | manager | contest | `confirmed`, `remove` or `withdraw` | `done`, what was done |
| `POST <task>/put-back` | manager | contest | | the boards' `notes` |
| `GET <task>` | observer | task | | the task's state |
| `GET <task>/publications` | observer | task | | the publications, oldest first, each with the `meanings` of the values its workflow reports |
| `GET <task>/workflow-form` | observer | task | | the inputs and test fields of the workflow the task names, or the `problem`, and whether the task is `graded` |
| `GET <task>/release` | a session | | | whether the caller sees the task and may submit to it now, or 404 when the contest is hidden from them |
| `GET <contest>/organise/entrants` | observer | contest | | every entrant, the earliest registered first, with its members and the invites into it |
| `POST <contest>/organise/entrants/{entrant_id}/approve` | manager | contest | | the entrant |
| `POST <contest>/organise/entrants/{entrant_id}/reject` | manager | contest | `reason` | the entrant |
| `POST <contest>/organise/entrants/{entrant_id}/reopen` | manager | contest | | the entrant, pending again |
| `POST <contest>/organise/entrants/{entrant_id}/remove` | manager | contest | | the entrant |
| `PUT <contest>/organise/entrants/{entrant_id}/extension` | manager | contest | `seconds`, `tasks` | the entrant |
| `PUT <contest>/organise/entrants/{entrant_id}/name` | manager | contest | `name` | the entrant |
| `DELETE <contest>/organise/entrants/{entrant_id}` | manager | contest | | 204 |
| `DELETE <contest>/organise/entrants/{entrant_id}/members/{user_id}` | manager | contest | | the entrant, or null when that left it with nobody and no submissions |
| `POST <contest>/organise/entrants/{entrant_id}/members/{user_id}/move` | manager | contest | `to` | the entrant the person is in now |
| `POST <task>/save` | manager | task | `changes`, `confirm`, `asked`, `keep_as_draft`, `message` | the save's result |
| `POST <task>/organise/uploads` | manager | task | `path`, `size`, `sha256`, `content_type` | 201, a slot |
| `GET <scope>/roles` | observer | scope | | the holders |
| `POST <scope>/roles` | manager | scope | `username`, `role` | 204 |
| `DELETE <scope>/roles/{user_id}` | manager | scope | | 204 |
| `GET <scope>/invites` | observer | scope | | the scope's invites, newest first |
| `POST <scope>/invites` | manager | scope | `grants`, `username` or `email`, `days`, `entrant` | 201, the invite |
| `POST <scope>/invites/{invite_id}/send-again` | manager | scope | | the invite, mailed again with a new link |
| `POST <scope>/invites/{invite_id}/withdraw` | manager | scope | | the invite, `withdrawn` |
| `GET <place>/tree?path=` | observer | place | | a folder's entries, each with its `upload` or null, its `token`, and a small text file's `start` |
| `GET <place>/files/{path}?at=` | observer | place | | `path`, `encoding`, `content`, `token`, `upload` |
| `GET <place>/history?path=` | observer | place | | every change, newest first |
| `PUT <place>/files/{path}` | manager | place | `encoding`, `content` or, at a task, `upload`, `token`, `message`, `confirm`, `asked`, `keep_as_draft` | `version` and `notes` at a contest, the save's result at a task |
| `POST <place>/files/{path}/rollback` | manager | place | `version`, `token`, `message`, `confirm`, `asked`, `keep_as_draft` | as a write |
| `GET <task>/gradings?limit=` | observer | task | | the task's gradings, newest first, each as the feed gives it |
| `GET <task>/gradings/{grading}/log` | observer | task | | the grading's run log, as plain text |
| `GET <task>/organise/submissions/{number}?entrant=` | observer | task | | a row's submission as the row reads it, with everything filled in |
| `POST <task>/gradings/{grading}/cancel` | manager | task | `reason` | the grading, `cancelled` with its `cancel_reason` |
| `POST <task>/gradings/{grading}/retry` | manager | task | | the new attempt, `queued` |
| `POST <task>/rejudge` | manager | task | | what the rejudge did, and the `regrade` it is kept as |
| `POST <task>/regrades/{regrade}/dismiss` | manager | task | | 204; the regrade's summary leaves the contest's page |
| `GET <task>/regrades/{regrade}` | manager | task | | a run task's regrade by each value and verdict it changed, old to new |
| `GET <contest>/gradings?task=&user=&entrant=&status=&latest=&regrade=&change=&limit=` | a role at the contest or at one of its tasks | contest | | the gradings of the tasks the caller observes, newest first, each with its `task`, `label` and `by`; with `regrade`, that regrade's, each with its `change` |
| `GET <contest>/gradings/queue` | a role at the contest or at one of its tasks | contest | | how many of theirs are `queued` and `dispatched`, and how many `failed` and wait |
| `GET <contest>/gradings/regrades` | a role at the contest or at one of its tasks | contest | | each task's latest regrade of many the caller observes, summed up by what it changed |
| `GET <place>/announcements` | observer | place | | every announcement, closed ones included, oldest first |
| `POST <place>/announcements` | manager | place | `title`, `body` | 201, the announcement |
| `PATCH <place>/announcements/{number}` | manager | place | `title`, `body` | the announcement |
| `POST <place>/announcements/{number}/close` | manager | place | | the announcement, `closed` |
| `POST <place>/announcements/{number}/reopen` | manager | place | | the announcement, open again; an open one is left as it is |
| `GET <org>/clarifications` | a role anywhere in the org | | | every question still open across the org, oldest first |
| `GET <contest>/clarifications` | observer | contest | | every question of the contest, answered ones included |
| `POST <contest>/clarifications/{asker}/{number}/replies` | manager | contest | `body` | the question, still open |
| `PUT <contest>/clarifications/{asker}/{number}/answered` | manager | contest | | the question, answered and closed |
| `DELETE <contest>/clarifications/{asker}/{number}/answered` | manager | contest | | the question, open again |
| `POST <contest>/clarifications/{asker}/{number}/announcement` | manager | contest | `title`, `body`, `mark` (default true) | 201, `{announcement, question}`: the announcement it made, and the question, marked answered unless `mark` is false, with a last message "Answered publicly in the announcement" and its title whose `announcement` is `{task, number, title}` (`task` null for the contest's own, `title` null once the message is edited at the forge); sent again after a failure part way it finishes that announcement instead of posting a second |

Creating an org, a contest or a task makes the whole thing at the forge
and the CI before the route answers, and the answer is the new thing's
`name`. A step that fails is refused with its reason, and asking again is
safe. An org's description is at most 255 characters, the most the forge
takes, on both the create and the change. `GET <org>` gives anyone
holding a role in the org, at it or at anything in it, the display name and
description as they stand at the forge, `display_name`
null while the org has none of its own. The person who asked becomes the
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
member of an entrant of that contest (`contestant_conflict`).

The invite routes are served under each of the three scope prefixes too. An
invite names a `username` or an `email`, and `grants` one of the three
roles at the scope or, at a contest, a place in it (`contestant`), straight
into the `entrant` named when the body names one; it stands for `days`, 14
unless given and at most 90. A member's invite into their entrant is
`member`, made by the member (below), never offered here: `grants` takes
the three roles and `contestant` alone. An invite carries `where`, the
scope's names, `contest_title`, the title of the contest it is at or
under, null at an org, `entrant`, the entrant it asks someone into, `{id, name}`,
or null, `invited_by`, its `status` (`pending`, `accepted`, `declined` or
`withdrawn`), `expired` for a pending one past `expires_at`, and
`mail_status`: `waiting` until the mail server takes it, `sent`, `failed`,
or `off` on a deployment with no mail server. The mail goes out after the
route answers, so a mail server that is down never fails the click. Forge
refuses a manager inviting an admin (`forbidden`), a place anywhere but a
contest, a target that is both or neither, and someone
who holds it already or could not take it (`invalid_invite`), a place at a
contest whose ways have no `invite` (`no_invite_way`), into an entrant
with no room (`entrant_full`), the same pending
invite twice (`already_invited`), and an org's thousand-and-first invite of
a day (`invite_limit`). Sending again makes a new link, so the old one
stops working, and gives the invite its whole lifetime again, a lapsed one
included; it is refused within ten minutes of the last mail
(`invite_limit`) and where the deployment sends no mail (`invalid_invite`).
Withdrawing takes back a pending invite, or an accepted place in a contest,
which otherwise lets its person in by the invite way when they register
again; anything else is `wrong_status`. A list shows
at most 500. A username whose account has no confirmed address gets no
mail, and its invite reads `failed`.

A contest's one kind of entry is the entrant, one or more people who enter
together, from `entrants.fewest` to `entrants.most` in `contest.yaml`, one
each by default. A contestant's entrant routes need a session alone, and
forge checks they are in the entrant they act for:
`POST <contest>/entrants` with a `name`, needed when entrants may be more
than one person, and the `code` a sign-up asks for, registers a new one
with the caller its first member; `GET <contest>/entrants/mine` is their
registration panel (below); `POST <contest>/entrants/mine/invites` with a
`username` or an `email` asks someone in, as an invite that `grants`
`member`, and `DELETE <contest>/entrants/mine/invites/{invite_id}` takes
one back; `POST <contest>/entrants/mine/leave` leaves, and
`PUT <contest>/entrants/mine/name` with a `name` renames it. Someone joins
an entrant by accepting an invite into it (below). An entrant's
submissions, the caps they count against, its extension and its questions
are its own, and a question on its desk is named `entrant.<id>`, the id's 32
hex digits. Refusals: `entrants_alone` (the contest's entrants are one
person each), `invalid_entrant_name`, `entrant_name_required`,
`entrant_name_taken`, `entrant_full` (with `limit`), `in_entrant`,
`entrant_has_submissions` and `entrant_changed` as 409 or 422 (below),
`roster_locked` (the roster locks at the contest's start, or at the
entrant's first submission when the contest says so, and from then on only
organisers change it) as 403, and `entrant_incomplete` (with `fewest` and
`members`) when an entrant short of members is approved or submits.

The person an invite is for acts on it with a session alone:
`GET /api/v1/me/invites` lists their pending invites, lapsed ones flagged,
including any sent to an address the forge has confirmed is theirs;
`POST /api/v1/me/invites/open` with the `token` after the `#` of the mail's
link opens one, in the body so the token never sits in a URL;
`POST /api/v1/me/invites/{invite_id}/accept`, with the `code` joining an
entrant may ask for, takes what it grants and answers with the `invite` and
`entered`: for a place in a contest, the `entrant` the person is in now,
`{id, name}`, its `status`, and `how`, whether accepting `made` it,
`joined` it or found them in it `already`, and null for a role;
`/decline` grants nothing, and either on a decided invite is
`wrong_status`. Anyone else's invite is `not_found`, a lapsed one is
`invite_expired` (410), and a link opened while the forge cannot say whose
address it is answers `forge_unavailable`. Accepting an organiser's place
registers the person by the contest's invite way, or puts them in the
entrant it names, and shows them a hidden contest while they are in no
entrant there.

## Files and the save

A file's content travels as text: `encoding` is `utf-8` when its bytes are
UTF-8 and `base64` when they are not, so a binary file makes the same round
trip. A file comes with the `token` it was read with, and a write sends that
token back, or null to create the file; a token that has moved since is
answered `conflict` with nothing written. Forge checks every path, and one
that is empty, absolute, climbs out with `..` or holds a character a URL or
git reads as something else is `invalid_path` before the forge is asked. A
write to `contest.yaml` that does not validate is `invalid_definition`,
with each error at its YAML path, one that opens the contest while a task
it lists is not published or its statement is not written among them, each
such task at `state` ("A · sum: its statement is not written yet."), and
a manager's change to one of its
admin-only keys is `admin_only`, naming each. A contest's file written
answers its `version` and `notes`, what each board reports of the tasks it
covers at that save, such as one that counts nothing from a task: the same
notes the organisers' reading carries beside each board, and none for any
other file. A rollback writes the file as
it was at an older version back as a new change, so the history stays
whole. The platform alone writes a contest's and a task's files at the
forge: every write, a rollback and a task's save included, is made by the
platform's account with the organiser as the change's author, so the
history names them, and the role checks in front of it, the guard's and
forge's own, are the only gate on it, each refusing before anything is
written.

A task is published by saving it. A write to a task's file, a rollback
there, and `POST <task>/save` are each a save, which `publications.save`
runs; the save route takes several files at once, each with its token. A save inside
`plans/` is `reserved_path`, and a manager's change to the task's name, its
`submissions` or `statement.md` is `admin_only`. A save that checks publishes,
and one that does not is kept as a draft: its files are written, nothing is
published, and the last publication keeps grading. Once the contest has
started, and until it is archived, every save that would publish something
new (files other than the latest publication's, or another plan) is
`confirmation_required`, and nothing is written. The refusal lists what
would change how the task grades (`changes`), how many submissions it
would grade again (`regrades`), and what the save does, laid out as the
page shows it: `results_change` and `summary` ("Results change." or
"Nobody's result changes."), then the sentences of `runs_again`,
`scores` and `reading` ("What entrants read"), each list holding at
least one, and `asked`, the head and latest publication it was worked out
from. The same save with `confirm` and that `asked` publishes while neither
has moved; once either has, it is asked again, so a change someone made
after the question is never published unread. A save with `keep_as_draft` is written as a draft that says what
it held back and publishes nothing, on any save, and an empty save with
`confirm` publishes that draft later.

A save answers with what it published or with the draft it kept. A
publication carries its `number`, `grading_changed`, the
`changes`, the `notes` the save makes of the task beside publishing it,
such as which steps it seals until the reveal, how many submissions it
`regraded`, queued to be graded again against it, and its `effect`, what
it did in the same fields and words as the question before it
(`results_change`, `summary`, `runs_again`, `scores`, `reading`); a draft carries the `version` written, the `errors`, each
`{path, message}`, and what it `held_back`. `GET <task>` answers the version at the head, the
latest publication or none, whether the head is a draft, and the draft's
errors, worked out again on every read, and whether the latest
publication's statement is written (`statement_written`: there, not blank
and not the starter's placeholder; false when nothing is published) and
the head's (`head_statement_written`). Opening a contest whose task's
published statement is not written is for the opening checklist to stop;
the forge itself does not check what opening needs.

`GET <contest>/organise/tasks` is the list an observer of the contest works
its tasks from: every task the contest's `tasks` lists, in that order, each
with its `task` by name, its `label`, the letter of its place, its `state`
as `GET <task>` gives it, and its `timeline` from its entry, each time at
its default where the entry gives none: `release_at`, `due`, null on a
task with no due, and `closes`; `withdrawn`, whether it is
withdrawn from the contest; `submissions`, how many it has, any entrant's;
and `take_out`, what taking it out would do, `remove` while it has none and
`withdraw` once it has, null while it is withdrawn. A withdrawn task keeps
its place and its letter. A task the contest does not
list is not on it. Settings that do not read answer `invalid_definition`, a
422 naming `contest.yaml`, with each of its `errors` at its `path`, as a
save of them would be refused.

`POST <task>/take-out` takes the task out of its contest, for a manager of
the contest, `confirmed` saying what the organiser agreed to, as the list's
`take_out` said: `remove`, while nobody has submitted to it, takes its entry
out of the contest's `tasks`, so the letters after it move up, and deletes
the task with its roles; `withdraw`, once anyone has, marks its entry
`withdrawn: true`, so it keeps its letter, entrants no longer see it, its
announcements or their own submissions to it, a submit to it is refused as
`task_withdrawn`, and no leaderboard counts it, its submissions kept for the
organisers. It answers `{"done": "remove"}` or `{"done": "withdraw"}`. When
it would now do the other, someone having submitted since the dialog
opened, it is `take_out_changed`, a 409 carrying `submissions` and
`take_out` as they are now; a leaderboard naming a task to be removed, or
settings that cannot be edited line by line, is `take_out_refused`, a 409,
with the `boards` that name it. `POST <task>/put-back` takes `withdrawn` out
of the entry again, checked as a save of the contest's settings is, an
entry that cannot be edited line by line being `take_out_refused`, and
answers the boards' `notes` as that save does; after it the task scores
exactly as before. Withdrawing a withdrawn task, or putting back one that
is not, changes nothing.

`GET <task>/workflow-form` is what the form over `task.yaml` is built from,
for an observer of the task: the `workflow` the task names as it is saved
now, a draft included, its `inputs`, each with its `id`, `type`, whether
the `contestant` gives it, its `options`, `per_test` and `optional`, and its
`test` fields, each with its `name`, `type` and `options`, in the
workflow's order. A workflow declares no defaults; a contestant input's
`default` is the task's own. A `task.yaml` that is missing or does not
read, names no workflow, or names one that cannot be read answers with
`problem`, the reason, and no inputs, so the form can still mend it.
Either way `graded` says whether the task has a graded submission, from
when on a save refuses a test group it adds without its `show`, and
`newer` names the workflow's version with the largest number when it is
larger than the one the task names, a tag under any other name never; the
task keeps grading with its own until it is saved
naming another.

A file too large to type, such as a dataset, goes into a task as an upload.
A manager of the task asks `POST <task>/organise/uploads` for a slot,
naming the `path` it is for, its `size` and `sha256`; the browser sends the
bytes through the same upload door a contestant's file goes through and
completes it with the same `POST <task>/uploads/{upload}/complete`, its
`input` empty. Nothing is in the task until a save names it: a change of
`POST <task>/save`, or the body of a task's `PUT <place>/files/{path}`,
gives `upload`, the upload's id, in place of `encoding` and `content`, and
the save writes the pointer to the file beside the other changes, one
commit and one publication. A change gives content or an upload, never both
or neither, and a contest's file takes no upload (`validation_error`). A
change of `POST <task>/save` may instead remove its file: `{"path", "token",
"remove": true}`, with the token the file was read with and no content or
upload (`validation_error` otherwise), a moved token being `conflict` as an
edit's is. Removing a folder, such as a test `tests/<group>/<test>/`, is
removing each file under it, named one by one, in the same save as any
files it is replaced by; the state left is checked as any other, so a
group left with no test or a file an input names removed keeps the save as
a draft with its errors, and the publication names each removed test file
among its `changes`. An upload that is not the caller's for that task and
path is
`invalid_inputs`, naming the path, and one whose bytes have not arrived
`upload_not_ready`. A file that is an upload is listed by the tree and read
with `upload`, the `size` and `digest` of what it holds, its `content` then
being the pointer, never opened as text; a typed file's `upload` is null.
Every file read names a `version` holding the file as read: the change
that last wrote it, or the `at` it was read at when that is a commit's id;
null otherwise. The tree names each file's `version` the same way, as
listed, so a file listed and not read downloads as it was listed. The
tree gives each file of at most 1 KB that is text (valid UTF-8, no NUL)
its `start`, its first 80 characters, the whole file when its UTF-8
length is the `size`, and an empty start for an empty file; a larger
file, one that is not text, and an upload, whose pointer is never shown,
have a null `start`. A task's `public/` lists empty until its first
file. A task's file, typed or uploaded,
is downloaded at that version through the proxy's download door,
`/-/downloads/<org>/<contest>/<task>/versions/<version>/<path>`, each
segment of the path quoted on its own, by whoever holds a role reaching the
task, observer or above, `plans/` included. The proxy asks this process
first, which answers with the forge's media endpoint for the file at that
commit, the organiser's own credential and the download's name, and streams
the file from the forge whatever its size, never through this process.
Anyone else, an entrant included, a path that is not plain, a segment
that decodes to one holding a slash (`%2F`), and a version that is not a
commit's id (40 or 64 lowercase hex) are refused alike, and a
file or a version the task does not have is the forge's refusal as it
serves; the proxy answers 404 to each.

`GET <task>/release` is what a contestant is told, and needs only a session:
whether the task is `released`, `visible` and `open` to the caller now by
the server's clock, and the first reason it is `closed`: `not_released`,
`archived` or `closed`. Nothing is released before the task's first
publication, nor a task the contest's `tasks` does not list, and a task
whose contest is hidden from the caller is not found.

## Contestants and visitors

A contestant's routes need a session and no role, since the person holds none
in the contest they enter:

| Route | Body | Answer |
|---|---|---|
| `GET /api/v1/contests` | | every published contest the caller may enter or has entered, newest start first, with their entrant's `status` |
| `POST <contest>/entrants` | `name`, `code` | 201, the caller's new entrant |
| `GET <contest>/entrants/mine` | | the caller's registration panel |
| `POST <contest>/entrants/mine/invites` | `username` or `email` | 201, the invite |
| `DELETE <contest>/entrants/mine/invites/{invite_id}` | | the invite, `withdrawn` |
| `POST <contest>/entrants/mine/leave` | | 204 |
| `PUT <contest>/entrants/mine/name` | `name` | the caller's entrant |
| `GET <contest>/home` | | the contest's home for the caller |
| `GET <task>/page` | | a released task's statement, its submission caps and the form of its inputs |
| `GET <contest>/home/announcements` | | the open announcements of the contest and of each task released to the caller |
| `GET <task>/page/announcements` | | the open announcements of a released task |
| `GET <task>/public/{path}` | | a file under the task's `public/`, as its bytes; no session needed, below |
| `POST <contest>/questions` | `title`, `body`, `task` | 201, the question, asked privately |
| `GET <contest>/questions` | | the caller's own questions, with every message |
| `POST <contest>/questions/{number}/comments` | `body` | the question, opened again when it was answered |
| `GET /api/v1/live` | | the session's live updates, as Server-Sent Events |

Registering answers pending, or approved when the entrant is complete and
the caller came in by a way that approves straight away. A registration
the contest's rules refuse answers with the rule's code:
`registration_closed`, `is_staff`, `invite_required`, `wrong_invite_code` and
`domain_not_allowed` as 403, `already_registered` and `contest_full` as 409.
An entrant carries its `id`, its own `name`, null for one of a contest
whose entrants are one person each, the `display_name` it is shown under,
its member's username then, its `status`, the `reason` when it was
rejected, its times, its `members`, each with the way they came in by,
`way_kind` (`invite`, `signup` or `organiser`) and `way_name`, the
`invites` into it still waiting, its extension: the `time_extension` in
seconds, on the `extension_tasks` by name, or on every task when that is
null, and whether it has `submitted`, is `complete` and is `locked`. The
panel carries the caller's `entrant`, or null, their own `invitations`
into the contest's entrants, whether the window is `registration_open`,
whether they `can_register` and, when they cannot, `refused`, the code and
sentence registering would answer, or `forge_unavailable` when their
confirmed addresses could not be read to say, `asks_code`, true only when a code
would let them in, and the contest's `most`, `fewest` and `locks`. The home
carries the contest `where` it is, its title as `name`, its dates and
`state`, the caller's panel as `registration`, whether the caller
`organises` the contest and so may not enter it, `now`, the server's clock
when it was read, and the `tasks` released to them, each
with its `name`, `label`, `title`, its `release`, when it falls `due`,
null when it has none, and `closes` for the caller, their entrant's
extension on it included; and, for a member of an approved entrant, its
`standing`: their own row on each leaderboard they read, as that board
shows it to them, so the home shows no number a board holds back. Anyone
else gets no standing. A task's page
carries the same, its `statement` in Markdown, its `submissions`: at most
`max` in all and `rate.count` in any `rate.per` seconds, and its `inputs`,
the form the submit panel is built from: each input's `id`, `type`
(`text`, `number`, `boolean`, `enum`, `file` or `folder`), `label` (the
task's, else the workflow's title for the input, else its key), the
`options` of an enum, whether it takes one file `per_test`, the `default` a
value takes when it is left out, `min` and `max` of a number, and
`max_size`, the most its files may total in bytes.
For a contest the caller may not see, the home answers 404, the same as for
one that is not there, and so does the page of a task that is not visible to
them; the panel's `entrant` reads null wherever they are in none.

The organiser's entrant routes are in the table above, and answer with
the entrant, each member's `user` carrying their `id`, `username`, `name`,
`email` and `avatar_url`, null once the account is gone. A decision the
entrant's status does not allow is `wrong_status`, carrying the status as
`current`; approving one short of members is `entrant_incomplete`; a
rejection needs a `reason` (`invalid_reason`). An extension moves the
entrant's due and close on the named `tasks`, or on every task when it
names none, in place of any it had. It is between none and a year, names
tasks the contest lists, and neither lets an entrant submit to a task whose
reveal has passed nor leaves one of its submissions after the due or the
close it was made before (`invalid_extension`); one of more than a billion
seconds either way is not taken at all (`validation_error`). Reopening
takes a rejection back: the entrant is pending again with its reason
cleared, and since it takes a place again it is refused with
`contest_full` when none is free and `is_staff` when a member holds a role
at the contest by now. Moving a member is refused with
`entrant_has_submissions` for the last member of an entrant that has
submitted, whose results would have nobody, and deleting an entrant that
has submitted the same way.

A visitor with no session calls the routes under `/api/v1/public`, which
read no cookie: `GET /api/v1/public/contests`, every contest whose
`visibility` is `everyone` and that is published; `GET
/api/v1/public/contests/{org}/{contest}`, one of them with its released
tasks; and `GET /api/v1/public/contests/{org}/{contest}/tasks/{task}`, a
released task's statement. Anything else answers 404 there. Every
contestant's and organiser's route answers a request with no session 401;
the few others that need none are the sign-in's own, the server's clock, the
health checks, the machines' doors and a task's public files, and a test
lists them all.

A task's public files, the ones under its `public/` such as a statement's
images, are read at `GET <task>/public/{path}`, `path` being the file's path
under `public/`, as the task's latest publication holds it, never a draft
saved after it. It reads the session when there is one and answers without:
a visitor, or a caller whose session has ended, reads it where the
statement is public; a signed-in caller where they read the task's page;
and a caller holding a role at the task, its contest or its org, whether or
not the task is released, as the task's head holds it, the draft the
statement's preview draws. A file that is an upload is answered with its
bytes, never its pointer. The answer is the bytes, typed by the file's
ending (`png`, `jpg`, `jpeg`, `gif`, `webp`, `svg`, `avif`, `apng`, `bmp`,
`ico`, in any case), `application/octet-stream` for anything else, with
`X-Content-Type-Options: nosniff`, `Cache-Control: private, no-cache` and
an `ETag` of the bytes, so the browser asks again each time and a picture a
save replaced shows at once (`If-None-Match` with the tag is a 304 while
the bytes are the same), and for an SVG `Content-Security-Policy: default-src 'none'; style-src
'unsafe-inline'; sandbox`, so one opened on its own runs no script. A path
with an empty, `.` or `..` segment, a file that is not there, and a task the
caller may not read are each `not_found`; a file larger than 10 MiB is
`public_file_too_large`, a 409 with the `limit` in bytes.

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

A file never passes through this process. The browser asks for a slot for
one file of a contestant `file` or `folder` input, declaring where it goes
under the input as its `filename`, one name for a file input, a path for a
folder input and `<group>/<test>` with or without an ending for an input
that takes a file per test, and its `size` and `sha256`, and the
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
`uploads` of its files, or the `value` of a text, number, true-or-false or
enum input, the language of a program being an enum input of its own; a
number is the text of its plain decimal digits, `2.5`, as every number is
served, and forge refuses one that is not (`1e3`, `0x10`, `NaN`, empty, or
past the input's bounds, checked exactly) as `invalid_inputs`, while a JSON
number in its place is a `validation_error`. It comes with
an `idempotency_key` the browser makes once per submit, 8 to 128 letters,
digits, `-` and `_`; a value left out takes its default. The same key sent
again answers with the submission it made and makes nothing. A submission
carries its `number`, `submitted_at` and its `grading`, the attempt that
counts, as the boards count it: the latest that finished with a result,
so a regrade under way, a failure or a cancel leaves the result as it was,
and while none has, the latest. It comes
with its `id`, `attempt` and `status`, and once it is `done`, what the
task's test groups let the contestant see now: what `stopped` the run, the
`outcome` over the groups shown, the `values` reported once, and each of
the `groups` with its `group` name, its `show`, its
`outcome` and its `tests`, each test's row being its `test`, `<group>/<test>`, its `outcome`
and its `values`; and `meanings`, every value the workflow reports, in its
order, each `{name, title, unit, fold, better}`, the title and unit being
the words a page names it by ("Run time", "ms"), null where the workflow
gives none so the page falls back to `name`, a value a sealed step holds
back left out until the reveal. A task graded test by test gives no
points. Every number is served exactly, as a
string of plain decimal digits, to 30 significant digits when it is no
decimal, and `values` come split into `numbers` and `texts`, so text that
looks like a number stays text. A group shown `always` carries everything; `verdict` its
outcome, and its tests from the task's reveal; `after_close` its name and,
as `shown_at`, when the rest is shown. A group with `ran` false did not
run on this grading: it has no outcome, no tests and nothing held back,
and the outcome over the groups leaves it out. What is not shown is null. A
grading's `status` is in the contestant's words, `queued`, `grading`,
`graded`, `delayed`, `over_limit` or `cancelled`, as `TASK-FORMAT.md`
section 1.7 has them; the gradings routes give organisers the grading's own
status. A
submission with no result whose run failed on the platform's side is
`delayed` to its contestant, with nothing else, and does not count against
the task's `max` meanwhile; it is tried again once by itself, and then
waits for staff, who grade it again or cancel it: then it is `cancelled`,
with `reason`, the sentence they gave, null on every other status, and the
submission no longer counts against the task's `max`. It is graded again
only while its entrant's submissions with a result and those waiting that
are not delayed, with the delayed ones made before it, are fewer than the
task's `max`, so the first `max` to get a result count; otherwise it is
`over_limit`, with `limit`, the `max` it reached, and nothing else ("Not
graded: you had reached the limit of 10 submissions for this task."),
counted on no board and against nothing; `limit` is null on every other
status. A submission that has a result keeps it, whatever its later
attempts read as. An outcome is one of the runner's list, and a value a number
or text. The route renders what forge gives it and nothing more. The files
route answers each input's `files`, by their paths in the submission, or
its `value`, a number as its exact digits.
A file itself is downloaded through the proxy's download door,
`/-/downloads/<org>/<contest>/<task>/<number>/<path>` (a task's own files go
through the same door at `.../<task>/versions/<version>/<path>`), which asks this
process whether the caller may read it and then streams it from the forge
as an attachment named after the file, so a file of any size passes
through the proxy and never through this process. Another contestant's submission is not found, the same as one
that is not there, and a number that cannot be one is `validation_error`.

A slot or a submit the task's rules refuse answers with the rule's code:
`task_closed`, with its `reason`, `closed` once the task has closed for
the caller, `task_withdrawn`, with its `reason`, `withdrawn`, for a task
withdrawn from its contest, `archived` and `not_approved` as 403; `submission_limit` with its `limit`,
`upload_not_ready` with the `uploads` refused, and `upload_limit`, too many
open uploads, with its `limit` and `bytes`, as 409; `rate_limited` as 429 with the `rate` and
`retry_at`, which the `Retry-After` header carries too; `too_large` as 413
with the `limit` in bytes and the `input` whose limit it is; `upload_not_yours` as 404 with the `uploads`; and `invalid_inputs`,
each of its `errors` naming its `input`, and `invalid_idempotency_key` as
422.

## Boards and marks

A contest's boards are worked out by forge on each read, for each reader:
staff read every board, row and cell with no hold; the members of an
approved entrant read `entrants` boards with their row as their own; and
anyone, with no cookie too, reads `everyone` boards.

| Route | Who | Answer |
|---|---|---|
| `GET /api/v1/public/contests/{org}/{contest}/boards` | anyone, no cookie | the boards for `everyone` |
| `GET /api/v1/public/contests/{org}/{contest}/boards/{board}` | anyone, no cookie | one of them |
| `GET <contest>/boards` | a session | the boards the caller reads, each as they read it |
| `GET <contest>/boards/{board}` | a session | one of them |
| `GET <contest>/hold` | observer at the contest | where the hold stands |
| `POST <contest>/hold/end` | manager at the contest | the hold, ended early |
| `GET <task>/marks` | a session | the marks the caller's row holds on the task |
| `PUT <task>/marks/{number}` | a session | the marks, with the submission marked |
| `DELETE <task>/marks/{number}` | a session | the marks, with its mark taken off |

A board carries its `key` and `title`, its `audience`, `{who, rows}`,
the `headers` of the columns listed to the caller, each with its `name`,
`places`, bounds and the values a contestant could set it by, its `sort`
keys and those `dropped` for the caller, `held_from`, when the hold
holds other rows from, and its `rows` in order. A row carries its
`place`, shared by rows equal on every sort key, whose it is as `row`,
`{entrant, name}`, its listed `cells`, each with its `column`, `number`
and `hidden`, `held`, how many of its submissions the hold keeps from
the caller, and, on the caller's own row and for staff, `grading`, how
many of its submissions still grade, each cell's `counted` and `waiting`
submissions, and whether it is `hidden`: on any other row `hidden` is
false, so a cell with no number reads the same whether it is hidden,
waiting or missing. Every number is an exact decimal string. A board the
reader may not see is not found.

A row, an entrant, marks up to the task's `marks` of its own
submissions for the `marked` boards, until its close on the task. Marks
carry the `numbers` marked, the `most`, `closes_at` and whether they are
`frozen`. Marking twice or unmarking what is not marked changes nothing. A
task with no marks is `marks_off` and one more than it takes is
`mark_limit` with its `limit`, both 409; a change after the close is
`marks_frozen`, 403; another row's submission is not found.


## Workflows

`POST /api/v1/workflows` makes a workflow and needs a session and no role.
The body names its `owner` and `name`; the owner is the caller's own
username, or the name of an org where they hold the manager role or above,
and forge decides which. The answer is 201 with the workflow's `owner` and
`name`, never its id at the forge, which is built from an org's key. The
workflow is private, and its first commit, a `workflow.yaml` named
`<owner>/<name>` with the inputs, test fields, steps and report of
`unicon/classic@v2`, is the caller's. An
observer of the org, a person with no role there, an org that is not there
and another person's username are all `forbidden`, in the same words, so the
answer tells nobody which orgs exist. A name that breaks the rules, or a
username that cannot name a workflow, is `invalid_name`, and a name the
owner has already is `conflict`.

Every other workflow route needs a session and no role too: forge decides
who may act on a workflow, the person it is named for or a manager or admin
of the org that owns it, and makes every change at the forge as the caller,
so the forge's own check is underneath. A workflow the caller may not read
is `not_found`, in the same words as one that is not there.

| Route | What it does |
|---|---|
| `GET /workflows` | every workflow the caller reaches, their own, their orgs', those shared with them and the platform's built-ins, by `owner` and `name`, with its `visibility`, its `versions` in natural order and whether it is `editable` |
| `GET /workflows/{owner}/{name}` | the same for one; for one the caller may edit, its `draft`, `content` and the `token` a save carries, and `readers`, the usernames it is shared with |
| `PUT /workflows/{owner}/{name}/draft` | write `workflow.yaml` over the one read with `token`, or create it with none, problems and all; `conflict` when it moved since |
| `POST /workflows/{owner}/{name}/versions` | freeze the saved draft under `version`, `v` and a whole number from 1 with no leading zero (`invalid_name` otherwise), 201, only when it passes every check a version must; otherwise `invalid_definition` with every problem in `errors` and no version made; given the `token` the draft was saved with, `conflict` when someone has saved since |
| `GET /workflows/{owner}/{name}/versions/{version}` | the `content` at a version, one of its tags and never a branch, read as the caller |
| `PUT /workflows/{owner}/{name}/visibility` | `private`, `shared` or `public`, 204; private and public empty the list of readers |
| `PUT /workflows/{owner}/{name}/readers/{username}` | share it with a person; `conflict` while it is public |
| `DELETE /workflows/{owner}/{name}/readers/{username}` | take their read away, 204 |
| `POST /workflows/check` | every problem a version of `content` would be refused for, each with its `path` and `message`; nothing is written |
| `POST /workflow-copies` | a new private workflow under `owner` from `source`, `<owner>/<name>@<version>`, 201 |
| `POST /workflow-combinations` | a new private workflow under `owner` inlining two or more `sources`, 201; one source is `rejected` |
| `GET /primitives` | every primitive at every version, its `ref` what a step's `use:` names, with `batch`, `network`, `limits`, `limits_from` and its `inputs` and `outputs`, each port's `type`, `options`, `optional`, `runs`, `secret` and `description`, and on the `outcome` port `outcomes`, each outcome the step can report with a line saying when, null when the primitive does not say; a version the platform no longer reads has `problem` instead |

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

A grading run calls these routes with no session, and each hands forge the
request as it arrived, since what admits it is over its exact bytes; a body
is read raw and only up to a bound, refused past it as `payload_too_large`
the way the event door refuses one.

`POST /api/v1/ci/config`, forge's `CI_CONFIG_PATH`, is where the CI asks
what a run is, called from inside the stack; the public proxy answers it
with 404. Its method, its target, the path undecoded and the query exactly
as sent, every header and the body, at most 1 MiB, go to `runs.config` as
an `InboundRequest`, which checks the CI's signature over them and answers
the run's steps; the route answers those bytes in the media type forge
gives. A request that does not verify, names no grading, or names one not
being started with its variables is `ci_request_refused`, never an empty
answer, and a CI that never asks is answered `not_found`.

`GET /api/v1/gradings/{grading}/envelope?key=` serves the envelope the
harness fetches as the run begins, for the envelope key the URL carries,
once, while the grading is dispatched; a wrong key is `not_found`, and a
second fetch, a grading the CI holds no run of, or one whose deadline has
passed, `grading_closed`. It carries the run's callback token,
so it is answered `Cache-Control: no-store`.

`POST /api/v1/gradings/{grading}/callback` takes a run's report, `started`,
`progress` or `finished` with the result, at most 4 MiB, handing the
`Authorization` header and the raw body to `runs.callback`, and answers the
grading's `status` after it. A missing or wrong bearer token is
`invalid_token`, a body that is no report `invalid_callback`, and a grading
that takes no reports now `grading_closed`. The same result sent again is
answered the same. Forge reads the body itself, every number exactly as the
run wrote it. `grading_closed` is a 410: a grading that has finished,
or whose run has ended, never takes an envelope or a report again.
`invalid_callback` is a 422
like every other body that does not fit. The harness stops reporting at a
401, 403, 404, 409 or 410 and sends a result again only after a 5xx or a
429, so each of these refusals ends a run's reporting and none is retried.
The request log never records the query or a header, so neither the key nor
the token reaches it.

A run task's Woodpecker step calls its own door, forge's `STEP_PATH`, with
`Authorization: Bearer <token>`, the step's own token, which each route
hands forge as it arrived with the raw body. `GET` on the door is the
step's job, answered as forge writes it, or 204 when nothing is left for
the step to do, which the step's wrapper ends on with success. `POST` on
the door, from the pipeline's report step only, at most 64 KiB, builds the
result and finishes the grading, answering its `status`. `POST
.../uploads`, at most 16 MiB, ten thousand paths, answers a presigned PUT
per file listed; `POST .../done`, at most 64 KiB, answers 204; and `GET
.../files/{sha256}` serves a file the step's job names as its bytes. The
job, the links and the files are answered `Cache-Control: no-store`. A
missing or wrong token, or one no longer working, is `invalid_token`, a
grading that has finished `grading_closed`, and a body that does not fit
`invalid_callback`.

An organiser managing a task ends a submission whose grading is a system
error by cancelling it, when a regrade would only repeat the fault, retries
a finished one as a new attempt, or rejudges the whole task against its
current publication, with the three routes in the organisers' table. A
grading is named under its task's prefix, where the guard checks the role,
and a grading of any other task is not found there, the same as one that is
not there at all, whatever the caller may do at that other task; forge
checks the role again at the grading's own task. A grading carries its
`id`, the `submission_number` and `submitted_at`, the `publication`,
`attempt`, `latest`, whether that is its submission's latest attempt, the
one staff cancel or retry, worked out over every attempt of it, `status`, `error`, the line for staff, `cancel_reason`, the
sentence staff cancelled it with, the `result` (what `stopped` the run, every
test's row in `tests`, the `values` reported once and the `error` it stopped
on), whether there is a `log`,
`progress` (the `step` last reported and how many of its containers are
`done` of the `total`) and its times. A cancel takes a body, `reason`, the
sentence the contestant reads, trimmed, of 1 to 500 characters
(`invalid_reason` otherwise), and cancels the latest attempt of a
submission that reads as `system_error`, stored or because its run is
overdue or lost, which keeps that as its `error`: cancelling ends the
submission, which a rejudge leaves as it is and a retry refuses. Cancelling
one that is not a system error, retrying one that is not finished, or
retrying a submission staff cancelled, is `wrong_status` with its `current`
status, `cancelled` for the last; cancelling or retrying an earlier attempt
of a submission graded again, or retrying one with another attempt still
being graded, is `conflict`. A grading that ends in `system_error` is
retried once by the platform itself, started by whatever finds it so, the
CI's report or any read that finds it overdue or lost (one whose run could
not be started waits a minute, for the first read after); that attempt is
`automatic`, and a failure of it waits for staff, who retry as often as
they like. Of a submission's attempts the latest that finished with a
result counts, on the boards, to its contestant and against the task's
`max`, until a newer attempt finishes with one: a failure or a cancel never
takes a result away, and a cancel voids only a submission that never had
one. A latest attempt that has not finished with a result carries
`last_good`, the latest earlier attempt that did, the one its submission
counts meanwhile, null when there is none. A retry or a rejudge of a
delayed submission whose entrant has no room left under the task's `max`
makes an attempt that ends `over_limit` at once, run by nothing, with
`limit`, the `max` it reached; a latest attempt of a submission with no
result that reads as `system_error` or `over_limit` carries `retry_limit`,
the task's `max` when a retry now would end so, null when it would grade
it, so the retry's confirmation can say so before it runs. `GET <task>/gradings` serves each grading as
the feed below does, with its task's name and label and who submitted it. A rejudge answers the
`publication` it grades against and how many attempts it `queued`,
`cancelled` first and `left_running`, and how many delayed submissions it
ended `over_limit`. A run's log names every test, hidden
ones too, so no contestant reads it. An observer of the task reads a
grading's log as `text/plain; charset=utf-8`, with `X-Content-Type-Options:
nosniff` and `Content-Security-Policy: default-src 'none'; sandbox`, so the
browser neither guesses its type nor runs anything in it. A grading with no
log is `not_found`, and a log larger than the 9 MiB read back is
`log_too_large`, a 409 with the `limit` in bytes.

Beside a grading, an observer of the task reads its submission as its row
reads it, with everything filled in (`TASK-FORMAT.md` section 1.7): `GET
<task>/organise/submissions/{number}` with the row's `entrant`, and a row
with no such submission `not_found`. It is the contestant's own payload, scored and shown by the
same code as once the task has revealed: every group's outcome and tests
and every value a sealed step reported. Each group's `shown_at` is kept as a note of when the row is
shown it, null once it sees the group's tests, and `status` is the
grading's own (`OrganisedResult`).

Anyone holding a role at a contest or at any of its tasks reads the
gradings of the tasks they observe as one feed, `GET <contest>/gradings`,
newest first, at most `limit` (100 unless given, at most 500): an observer
of the contest, or of its org, every task's, and someone holding a role at
some of its tasks alone those tasks', a task they do not observe giving no
rows. Each row is the `grading` as above, its `task` by name, its `label`,
the letter of its place in the contest's `tasks`, null once the contest no
longer lists it or its settings do not read, and `by`, whose submission
it is: the `entrant` by id and `entrant_name`, the name it is shown under,
and the member who submitted it by `user_id` and `username`, null when a
reconcile found the submission at the forge. Every attempt is a row of
its own, so a submission graded again shows more than once. `task` narrows
the feed to a task by name, `user` to the submissions a member made, by
username, `entrant` to an entrant's, by id, `status` to the gradings that
read as it, an overdue or lost one counting as `system_error`, and
`latest=true` to each submission's latest attempt; a task,
username or entrant the contest does not have gives no rows. A `user` that
breaks Forgejo's rule for a username (letters, digits, `-`, `_` and `.`,
beginning and ending with a letter or a digit, no two of `-`, `_` and `.`
side by side, at most 40 characters), or an `entrant` that is not a UUID,
is a `validation_error`.
`GET <contest>/gradings/queue` counts the contest's gradings waiting for a
machine, `queued`, whose run is not started yet, and `dispatched`, whose
run the CI holds until a machine takes it, when asked, one overdue or lost
reading as a system error and not counted there; and `failed`, the latest
attempts that read as a system error, which wait for their retry or for
staff: the gradings `?status=system_error&latest=true` lists, so the
contest's page can say "2 gradings failed" and link to them. Both read the
same tasks the feed reads.

A rejudge, and the regrade a save that changes how a task grades starts,
is kept as one regrade of many; its attempts, and each retry of one of
them, carry its id as `regrade`, and a rejudge answers it, null when it made
no attempt. `GET <contest>/gradings/regrades` gives, over the tasks the feed
reads, each task's latest regrade, newest first, until a newer one of the
task replaces it or a manager of the task dismisses it for everyone with
`POST <task>/regrades/{regrade}/dismiss` (204; a regrade of another task
is `not_found`), so the contest's page and the gradings page can say
"Regrade of A: 120 graded · 4 went down · 2 now fail to compile · 1 went
up". Each summary has its `id`, its `task` by name and `label`, its `cause`,
`rejudge` or `save`, the `publication` its attempts grade against,
`started_at`, `started_by` and `started_by_name`, how many submissions it
took (`total`) and `graded` (finished with a result), whether any is still
`running`, and `counts`, how many of each change: `up` and `down`, a
larger or smaller share of its tests accepted; `stopped`, it now stops before its tests where the
result it replaced did not, on the classic workflow "now fails to compile";
`unchanged`; `new`, graded with nothing to compare with; `running`;
`failed`, no result yet, a system error or cancelled; and `over_limit`.
The feed with `regrade=<id>` lists that regrade's gradings, one per
submission, its latest attempt of the regrade, each with `change`: the
`change`, `earlier`, the result that counted when the regrade began, and
`now`, its own, each with its `attempt`, `accepted` of `tests` and what
`stopped` it, so the earlier and new read side by side; `change=` narrows them to one kind, and `user` and `entrant` narrow
as ever, while `task`, `status` and `latest` are not read with it. `change`
without `regrade` gives no rows.

A run task's regrade has no direction per value: up and down are a row's
place on a board. `GET <task>/regrades/{regrade}`, for a manager of the
task, reads it by what it changed, worked out on read and stored nowhere:
`total`, how many are still `running` and how many `failed` with no
result, and `changed`, each submission whose values or verdicts moved, in
the order they were made, with its latest attempt of the regrade
(`grading`), its `number`, each value `before` and `after` (exact, null
where it had none or waits, `waiting` after) and each run's verdict
`before` and `after`. `boards`, each board that reads the task before and
after, is given to a manager or admin of the contest alone, null for
anyone else, and empty until boards read a run task's values. A regrade of
another task, or of a task graded test by test, is `not_found`.

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
| `forbidden`, `ci_request_refused`, `fresh_sign_in_required`, `origin_mismatch`, `admin_only`, `reserved_path`, `registration_closed`, `is_staff`, `invite_required`, `wrong_invite_code`, `domain_not_allowed`, `roster_locked`, `task_closed`, `task_withdrawn`, `archived`, `not_approved`, `marks_frozen` | 403 |
| `conflict`, `sole_admin`, `contestant_conflict`, `shared_workflow_owner`, `confirmation_required`, `already_registered`, `contest_full`, `already_invited`, `no_invite_way`, `entrants_alone`, `entrant_name_taken`, `entrant_full`, `in_entrant`, `entrant_incomplete`, `entrant_has_submissions`, `entrant_changed`, `wrong_status`, `submission_limit`, `upload_not_ready`, `upload_limit`, `marks_off`, `mark_limit`, `log_too_large`, `public_file_too_large`, `take_out_changed`, `take_out_refused` | 409 |
| `grading_closed`, `invite_expired` | 410 |
| `payload_too_large`, `too_large` | 413 |
| `rate_limited`, `invite_limit` | 429, with `Retry-After` |
| `rejected`, `invalid_name`, `invalid_definition`, `invalid_path`, `invalid_reason`, `invalid_extension`, `invalid_invite`, `invalid_entrant_name`, `entrant_name_required`, `invalid_inputs`, `invalid_idempotency_key`, `invalid_callback`, `invalid_message`, `validation_error` | 422 |
| `unauthenticated`, `session_expired` | 401, and the session cookie is cleared |
| `invalid_token` | 401 |
| `sign_in_invalid`, `sign_in_denied` | 400 |
| `forge_misconfigured` | 502 |
| `forge_unavailable` | 503 |

`sole_admin` carries `scopes`, each `{"kind", "name"}`,
`contestant_conflict` carries `contests`, `shared_workflow_owner` carries
`workflows`, `admin_only` carries `keys`, `reserved_path` carries `paths`,
`confirmation_required` carries `changes`, `regrades`, `results_change`,
`summary`, `runs_again`, `scores`, `reading` and `asked`, `take_out_changed`
carries `submissions` and `take_out`, `take_out_refused` carries `boards`
when a leaderboard names the task, `already_invited` carries `invite`,
the one held already, `invalid_definition` carries
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
installed from it as it stands when `uv sync` builds it. The image then
builds with that checkout handed in as the named
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
