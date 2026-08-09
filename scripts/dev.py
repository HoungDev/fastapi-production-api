"""Cross-platform local-development commands for contributors."""

from __future__ import annotations

import argparse
import secrets
import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ENV_TEMPLATE = PROJECT_ROOT / ".env.example"
ENV_FILE = PROJECT_ROOT / ".env"
SECRET_PLACEHOLDER = "change_this_to_a_random_secret_key"
RATE_LIMIT_SECRET_PLACEHOLDER = "change_this_to_a_random_rate_limit_key"


class DevelopmentError(RuntimeError):
    """Raised when the local development environment cannot be prepared."""


def require_command(command: str) -> None:
    if shutil.which(command) is None:
        raise DevelopmentError(
            f"Required command '{command}' was not found on PATH. "
            "See DEVELOPMENT.md for installation instructions."
        )


def run_command(command: list[str]) -> None:
    print(f"\n> {' '.join(command)}", flush=True)
    subprocess.run(command, cwd=PROJECT_ROOT, check=True)


def require_docker_engine() -> None:
    require_command("docker")
    result = subprocess.run(
        ["docker", "info"],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise DevelopmentError(
            "Docker engine is unavailable. Start Docker Desktop, select Linux "
            "containers, and verify that 'docker info' succeeds."
        )


def ensure_env() -> bool:
    """Create a local .env with a generated secret, without overwriting one."""
    if ENV_FILE.exists():
        print("Using existing .env file.")
        return False

    template = ENV_TEMPLATE.read_text(encoding="utf-8")
    if (
        SECRET_PLACEHOLDER not in template
        or RATE_LIMIT_SECRET_PLACEHOLDER not in template
    ):
        raise DevelopmentError(
            ".env.example does not contain the expected secret placeholders."
        )

    generated_secret = secrets.token_urlsafe(48)
    generated_rate_limit_secret = secrets.token_urlsafe(48)
    ENV_FILE.write_text(
        template.replace(SECRET_PLACEHOLDER, generated_secret, 1).replace(
            RATE_LIMIT_SECRET_PLACEHOLDER,
            generated_rate_limit_secret,
            1,
        ),
        encoding="utf-8",
    )
    print("Created .env with a generated local SECRET_KEY.")
    return True


def setup(*, skip_docker: bool = False) -> None:
    require_command("uv")
    ensure_env()
    run_command(["uv", "sync", "--locked", "--all-groups"])

    if not skip_docker:
        require_docker_engine()
        run_command(["docker", "compose", "up", "-d", "--wait", "postgres", "redis"])

    run_command(["uv", "run", "alembic", "upgrade", "head"])
    print("\nSetup complete. Start the API with: python scripts/dev.py serve")


def serve() -> None:
    require_command("uv")
    run_command(
        [
            "uv",
            "run",
            "uvicorn",
            "app.main:app",
            "--reload",
            "--host",
            "127.0.0.1",
            "--port",
            "8000",
        ]
    )


def migrate() -> None:
    require_command("uv")
    run_command(["uv", "run", "alembic", "upgrade", "head"])


def services_up() -> None:
    require_docker_engine()
    run_command(["docker", "compose", "up", "-d", "--wait", "postgres", "redis"])


def database_down() -> None:
    require_docker_engine()
    run_command(["docker", "compose", "down"])


def check() -> None:
    require_command("uv")
    commands = [
        ["uv", "run", "ruff", "check", "."],
        ["uv", "run", "ruff", "format", "--check", "."],
        ["uv", "run", "alembic", "upgrade", "head"],
        ["uv", "run", "pytest", "--cov-report=xml"],
        ["uv", "run", "pip-audit"],
        ["uv", "build"],
    ]
    for command in commands:
        run_command(command)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Prepare, run, and validate the local development environment."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    setup_parser = subparsers.add_parser(
        "setup",
        help="Create .env, install dependencies, start services, and migrate.",
    )
    setup_parser.add_argument(
        "--skip-docker",
        action="store_true",
        help="Use dependency URLs in .env without starting Docker Compose.",
    )
    subparsers.add_parser("serve", help="Run the API locally with auto-reload.")
    subparsers.add_parser("migrate", help="Apply all database migrations.")
    subparsers.add_parser(
        "db-up", help="Start and wait for local PostgreSQL and Redis."
    )
    subparsers.add_parser("db-down", help="Stop local Compose services.")
    subparsers.add_parser("check", help="Run the complete CI-equivalent quality gate.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    actions = {
        "serve": serve,
        "migrate": migrate,
        "db-up": services_up,
        "db-down": database_down,
        "check": check,
    }

    try:
        if args.command == "setup":
            setup(skip_docker=args.skip_docker)
        else:
            actions[args.command]()
    except DevelopmentError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    except subprocess.CalledProcessError as error:
        print(
            f"Error: command failed with exit code {error.returncode}.",
            file=sys.stderr,
        )
        return error.returncode or 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
