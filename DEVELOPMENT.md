# Local development

This guide covers the shortest supported setup path, everyday contributor
commands, and common local failures. The helper uses only the Python standard
library and runs the same underlying `uv`, Docker Compose, Alembic, Ruff, and
Pytest commands documented by the project.

## Requirements

- Python 3.13 or newer
- [uv](https://docs.astral.sh/uv/getting-started/installation/)
- Docker with the Compose v2 plugin, or reachable PostgreSQL 17 and Redis services

Check the tools before setup:

```bash
python --version
uv --version
docker compose version
```

## One-command setup

From the repository root, run:

```bash
python scripts/dev.py setup
```

The command performs these idempotent steps:

1. Copies `.env.example` to `.env` when needed and generates a local
   `SECRET_KEY`. An existing `.env` is never overwritten.
2. Installs the exact locked development dependencies.
3. Starts PostgreSQL and Redis and waits for their health checks.
4. Applies all Alembic migrations.

To use PostgreSQL and Redis outside Docker, set `DATABASE_URL` and `REDIS_URL`
in `.env` first and run:

```bash
python scripts/dev.py setup --skip-docker
```

## Run the API

```bash
python scripts/dev.py serve
```

Open <http://127.0.0.1:8000/docs>. To create a local user, call `POST
/register/` from Swagger UI; the repository intentionally does not ship a
shared demo password.

## Run durable email workers

Generate a dedicated Fernet key, set `EMAIL_DELIVERY_MODE=outbox`, configure
SMTP, apply migrations, and start a worker in a second terminal:

```bash
uv run fastapi-production-worker
```

Start additional identical processes to test horizontal claims. For one
deterministic batch without polling, use:

```bash
uv run fastapi-production-worker --once
```

Workers stop claiming on `SIGTERM`/`SIGINT`. They finish in-flight work within
the configured grace period; abandoned leases become claimable after expiry.
Never run workers against a database while its `OUTBOX_ENCRYPTION_KEY` is
missing or different from the key used to enqueue pending payloads.

## Everyday commands

| Command | Purpose |
| --- | --- |
| `python scripts/dev.py db-up` | Start PostgreSQL and Redis and wait until healthy |
| `python scripts/dev.py db-down` | Stop Compose services without deleting data |
| `python scripts/dev.py migrate` | Apply pending Alembic migrations |
| `python scripts/dev.py serve` | Run Uvicorn with auto-reload |
| `python scripts/dev.py check` | Run lint, format check, migrations, tests, audit, and build |

The helper is a convenience layer. Individual commands remain available for
focused work, for example `uv run pytest tests/test_login.py` or `uv run ruff
format .`.

To run the real Redis concurrency and TTL tests against the local Compose
service in PowerShell:

```powershell
$env:REDIS_TEST_URL='redis://localhost:6379/15'; uv run pytest tests/test_redis_rate_limit_integration.py
```

The test database is flushed before and after these tests. Never point
`REDIS_TEST_URL` at a shared or production Redis database.

Worker concurrency tests require PostgreSQL because SQLite does not implement
`FOR UPDATE SKIP LOCKED`. The standard CI job runs these tests on PostgreSQL.

## Typical contribution workflow

```bash
git switch main
git pull --ff-only
git switch -c fix/short-description
python scripts/dev.py setup
python scripts/dev.py check
```

Commit only source files and intentional lock-file changes. `.env`, databases,
coverage output, and distributions are ignored by Git.

## Troubleshooting

### Port 5432 or 6379 is already in use

Stop the conflicting service, or point `DATABASE_URL` and `REDIS_URL` at
reachable dependencies and use `setup --skip-docker`. Do not run duplicate
services on the same host ports.

### PostgreSQL or Redis does not become healthy

Inspect the containers with `docker compose ps`, `docker compose logs postgres`,
and `docker compose logs redis`. Confirm Docker has enough disk space and that
Compose values match the local dependency URLs.

### Docker reports an API 500 or cannot reach the Linux engine

Start or restart Docker Desktop, confirm it is using Linux containers, and run
`docker info`. The setup helper stops early with a focused message until that
command succeeds; no project data is changed by this preflight check.

### Migrations cannot connect

Run `python scripts/dev.py db-up`, then check `docker compose ps`. If you use an
external database, verify its hostname, port, database name, and credentials in
`.env`.

Environment variables in the current shell take precedence over `.env`. If
Alembic reports an unexpected database backend, inspect `DATABASE_URL` with
`echo $DATABASE_URL` on Unix or `$env:DATABASE_URL` in PowerShell, clear the
stale value, and open a new terminal if necessary.

### Recreate the local database

`docker compose down --volumes` permanently deletes the local Compose database
volume. Use it only when the data is disposable, then rerun `python
scripts/dev.py setup`.

### The quality gate changes files or fails

Apply formatting with `uv run ruff format .`, rerun the focused failing test,
and then run `python scripts/dev.py check` again. The coverage gate requires at
least 90% combined statement-and-branch coverage.
