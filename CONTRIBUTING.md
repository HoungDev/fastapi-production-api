# Contributing to FastAPI Production API

Thank you for helping make this FastAPI foundation more secure, reliable, and
useful. Contributions to code, tests, documentation, issue triage, and examples
are all welcome.

By participating, you agree to follow the [Code of Conduct](CODE_OF_CONDUCT.md).

## Before you start

- Search existing issues and pull requests before opening a duplicate.
- Use GitHub Discussions for usage questions and early-stage ideas.
- Open an issue before starting a large or breaking change.
- Never report a suspected vulnerability in a public issue; follow
  [SECURITY.md](SECURITY.md).

Issues labeled `good first issue` are intentionally small and suitable for a
first contribution. Issues labeled `help wanted` have an agreed direction and
are ready for community implementation.

## Development setup

### Requirements

- Python 3.13+
- [uv](https://docs.astral.sh/uv/)
- Docker, or a local PostgreSQL server

```bash
git clone https://github.com/HoungDev/fastapi-production-api.git
cd fastapi-production-api
cp .env.example .env
docker compose up -d postgres
uv sync --locked --all-groups
uv run alembic upgrade head
```

On PowerShell, use `Copy-Item .env.example .env` instead of `cp`.

Generate a development secret and place it in `.env`:

```bash
uv run python -c "import secrets; print(secrets.token_urlsafe(48))"
```

## Make a focused change

Create a branch from the latest `main`:

```bash
git switch main
git pull --ff-only
git switch -c fix/short-description
```

Keep commits focused. Recommended commit prefixes are:

```text
feat: add a backward-compatible capability
fix: correct broken behavior
docs: improve documentation
test: add or improve coverage
refactor: restructure without changing behavior
chore: maintain tooling or dependencies
```

## Run the quality gate

Before opening a pull request, run:

```bash
uv run ruff check .
uv run ruff format --check .
uv run alembic upgrade head
uv run pytest
uv run pip-audit
uv build
```

The test command enforces the repository's 90% statement-and-branch coverage
gate. New behavior should include focused assertions for success, failure, and
authorization paths rather than tests written only to increase the percentage.

Use `uv run ruff format .` to apply the project formatter. New behavior must
include tests. Changes to configuration, endpoints, or deployment behavior must
also update the relevant documentation.

## Open a pull request

A reviewable pull request should:

- solve one clearly described problem;
- link its issue with `Fixes #123` when applicable;
- explain user-visible and security impact;
- include tests or explain why tests are not needed;
- preserve backward compatibility, or explicitly document the break;
- contain no credentials, personal data, generated databases, or build output.

Maintainers may ask for a smaller scope when a pull request mixes unrelated
changes. This keeps reviews fast and makes releases safer.

## Reporting bugs

Use the bug report template and include:

- the smallest reproducible example;
- expected and actual behavior;
- operating system and Python version;
- project version or commit SHA;
- database and deployment environment;
- redacted logs or stack traces.

Thank you for contributing.
