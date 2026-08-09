import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "dev.py"
SPEC = importlib.util.spec_from_file_location("dev_script", SCRIPT_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"Unable to load development helper from {SCRIPT_PATH}")
dev = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = dev
SPEC.loader.exec_module(dev)


def configure_env_paths(monkeypatch, tmp_path: Path) -> None:
    template = tmp_path / ".env.example"
    template.write_text(
        f"SECRET_KEY={dev.SECRET_PLACEHOLDER}\nDEBUG=true\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(dev, "ENV_TEMPLATE", template)
    monkeypatch.setattr(dev, "ENV_FILE", tmp_path / ".env")


def test_ensure_env_generates_secret_without_leaving_placeholder(monkeypatch, tmp_path):
    configure_env_paths(monkeypatch, tmp_path)
    monkeypatch.setattr(dev.secrets, "token_urlsafe", lambda _: "generated-secret")

    created = dev.ensure_env()

    assert created is True
    assert dev.ENV_FILE.read_text(encoding="utf-8") == (
        "SECRET_KEY=generated-secret\nDEBUG=true\n"
    )


def test_ensure_env_does_not_overwrite_existing_file(monkeypatch, tmp_path):
    configure_env_paths(monkeypatch, tmp_path)
    dev.ENV_FILE.write_text("SECRET_KEY=existing\n", encoding="utf-8")

    created = dev.ensure_env()

    assert created is False
    assert dev.ENV_FILE.read_text(encoding="utf-8") == "SECRET_KEY=existing\n"


def test_setup_prepares_dependencies_database_and_migrations(monkeypatch):
    monkeypatch.setattr(dev, "require_command", lambda _: None)
    monkeypatch.setattr(dev, "require_docker_engine", lambda: None)
    monkeypatch.setattr(dev, "ensure_env", lambda: True)
    commands = []
    monkeypatch.setattr(dev, "run_command", commands.append)

    dev.setup()

    assert commands == [
        ["uv", "sync", "--locked", "--all-groups"],
        ["docker", "compose", "up", "-d", "--wait", "postgres"],
        ["uv", "run", "alembic", "upgrade", "head"],
    ]


def test_setup_can_use_an_existing_database(monkeypatch):
    required_commands = []
    monkeypatch.setattr(dev, "require_command", required_commands.append)
    monkeypatch.setattr(dev, "ensure_env", lambda: False)
    commands = []
    monkeypatch.setattr(dev, "run_command", commands.append)

    dev.setup(skip_docker=True)

    assert required_commands == ["uv"]
    assert commands == [
        ["uv", "sync", "--locked", "--all-groups"],
        ["uv", "run", "alembic", "upgrade", "head"],
    ]


def test_check_matches_the_repository_quality_gate(monkeypatch):
    monkeypatch.setattr(dev, "require_command", lambda _: None)
    commands = []
    monkeypatch.setattr(dev, "run_command", commands.append)

    dev.check()

    assert commands == [
        ["uv", "run", "ruff", "check", "."],
        ["uv", "run", "ruff", "format", "--check", "."],
        ["uv", "run", "alembic", "upgrade", "head"],
        ["uv", "run", "pytest", "--cov-report=xml"],
        ["uv", "run", "pip-audit"],
        ["uv", "build"],
    ]


def test_main_returns_failed_command_exit_code(monkeypatch):
    def fail() -> None:
        raise dev.subprocess.CalledProcessError(7, ["uv", "build"])

    monkeypatch.setattr(dev, "check", fail)

    assert dev.main(["check"]) == 7


def test_database_commands_use_compose_without_deleting_data(monkeypatch):
    monkeypatch.setattr(dev, "require_docker_engine", lambda: None)
    commands = []
    monkeypatch.setattr(dev, "run_command", commands.append)

    dev.database_up()
    dev.database_down()

    assert commands == [
        ["docker", "compose", "up", "-d", "--wait", "postgres"],
        ["docker", "compose", "down"],
    ]
    assert ["docker", "compose", "down", "--volumes"] not in commands


def test_docker_preflight_explains_unavailable_engine(monkeypatch):
    monkeypatch.setattr(dev, "require_command", lambda _: None)
    monkeypatch.setattr(
        dev.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=1),
    )

    with pytest.raises(dev.DevelopmentError, match="Docker engine is unavailable"):
        dev.require_docker_engine()
