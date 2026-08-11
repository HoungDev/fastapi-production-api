from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_production_image_is_locked_minimal_and_non_root():
    dockerfile = (PROJECT_ROOT / "Dockerfile").read_text(encoding="utf-8")

    assert "uv sync --locked --no-dev --no-editable" in dockerfile
    assert "FROM python:3.13-slim-trixie AS runtime" in dockerfile
    assert "USER 10001:10001" in dockerfile
    assert "HEALTHCHECK" in dockerfile
    assert 'CMD ["fastapi-production-api"]' in dockerfile


def test_docker_context_excludes_secrets_and_local_environments():
    dockerignore = (PROJECT_ROOT / ".dockerignore").read_text(encoding="utf-8")

    assert dockerignore.startswith("**\n")
    assert "!.env" not in dockerignore
    assert "!.venv" not in dockerignore
    assert "!src/**" in dockerignore


def test_compose_runs_migrations_before_the_api_with_runtime_hardening():
    compose = (PROJECT_ROOT / "docker-compose.yml").read_text(encoding="utf-8")

    assert "service_completed_successfully" in compose
    assert 'command: ["alembic", "upgrade", "head"]' in compose
    assert compose.count("read_only: true") == 2
    assert compose.count("no-new-privileges:true") == 2
