# Unicon backend

Unicon runs programming contests. This repo is its HTTP layer: a thin
FastAPI app over the `forge` package, which holds every rule, the Postgres
tables and the adapters. Both run as one process.

It ships two things: the `backend` image and [`openapi.json`](openapi.json),
which the frontend generates its API types from.

The other repos are `forge`, `frontend`, `runner`, `primitive-exec` and
`deploy` (the compose stack, proxy, bootstrap and dev seed).

## Run it locally

You need [uv](https://docs.astral.sh/uv/) and a Postgres. Run everything
from the repo root.

```sh
uv sync
cp .env.example .env          # then fill in the empty values
set -a; . ./.env; set +a
uv run unicon-forge migrate   # forge's command; this repo has no migrations
uv run unicon api             # http://localhost:8000
```

[`.env.example`](.env.example) points at the `deploy` dev stack's services.
Every `UNICON_*` setting is read by forge, not by this repo.
`UNICON_FORGE=fake` runs against forge's in-memory fake instead of a git host.

`unicon create-org` and `unicon create-account` are operator commands. Run
`uv run unicon --help` to see them.

## Test it

CI runs these in order:

```sh
uv sync --frozen
uv run ruff format --check .
uv run ruff check .
uv run lint-imports
uv run mypy
UNICON_TEST_DATABASE_URL=postgresql+psycopg://postgres:test@localhost:5432/postgres uv run pytest -n 4
```

`tests/unit` needs no database. `tests/integration` runs the app over a real
Postgres and forge's in-memory fake. It creates and drops its own database
on the server `UNICON_TEST_DATABASE_URL` names, and is skipped when that is
not set.

After any change to a route or schema, regenerate `openapi.json` and commit
it. CI fails if it is stale:

```sh
uv run unicon openapi
git diff --exit-code openapi.json
```

## Developing against an unreleased forge

During development `[tool.uv.sources]` in `pyproject.toml` points at the
sibling checkout `../forge`. The image then needs that checkout passed in:

```sh
docker build --build-context forge=../forge .
```

CI checks out this repo alone, so it only passes with a released forge pinned.

## Release

1. Once forge is released, pin it in `pyproject.toml`: set
   `unicon-forge==<version>` in `dependencies`, and point
   `[tool.uv.sources]` at the wheel:
   `https://github.com/uniconhq/forge/releases/download/v<version>/unicon_forge-<version>-py3-none-any.whl`.
   Then run `uv lock`.
2. Bump `version` in `pyproject.toml`.
3. Run `uv run unicon openapi`. The document's version is the package's.
4. Merge to `main`. CI builds and pushes `ghcr.io/uniconhq/backend:main` and
   `ghcr.io/uniconhq/backend:sha-<short commit>`.
5. Tag `v<version>` on `main`. No workflow runs on the tag.

## Don't break

- The backend and its tests import forge only through `forge.api` (and the
  tests also `forge.testing`). `lint-imports` enforces this. If something is
  missing, add it to `forge.api` in forge.
- The app under `unicon/` never imports `forge.testing`.
- The app has no tables, migrations or settings of its own. Those live in
  forge.
- Error codes map to HTTP statuses in `unicon/api/errors.py` only.
- The request log records method, path, status and duration. Never the
  query string, cookies or body.

MIT licence. See [`LICENSE`](LICENSE).
