# Local development

This guide covers the shortest supported setup path, everyday contributor
commands, and common local failures. The helper uses only the Python standard
library and runs the same underlying `uv`, Docker Compose, Alembic, Ruff, and
Pytest commands documented by the project.

## Requirements

- Python 3.13 or newer
- [uv](https://docs.astral.sh/uv/getting-started/installation/)
- Docker with the Compose v2 plugin, or a reachable PostgreSQL 17 server

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
3. Starts PostgreSQL and waits for its health check.
4. Applies all Alembic migrations.

To use PostgreSQL outside Docker, set `DATABASE_URL` in `.env` first and run:

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

## Everyday commands

| Command | Purpose |
| --- | --- |
| `python scripts/dev.py db-up` | Start PostgreSQL and wait until it is healthy |
| `python scripts/dev.py db-down` | Stop Compose services without deleting data |
| `python scripts/dev.py migrate` | Apply pending Alembic migrations |
| `python scripts/dev.py serve` | Run Uvicorn with auto-reload |
| `python scripts/dev.py check` | Run lint, format check, migrations, tests, audit, and build |

The helper is a convenience layer. Individual commands remain available for
focused work, for example `uv run pytest tests/test_login.py` or `uv run ruff
format .`.

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

### Port 5432 is already in use

Either stop the other PostgreSQL service or point `DATABASE_URL` at it and use
`setup --skip-docker`. Do not run two database servers on the same host port.

### PostgreSQL does not become healthy

Inspect the container with `docker compose ps` and `docker compose logs
postgres`. Confirm Docker has enough disk space and that the values in
`docker-compose.yml` match the local `DATABASE_URL`.

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
