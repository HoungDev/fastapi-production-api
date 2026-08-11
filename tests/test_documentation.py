import re
from pathlib import Path
from urllib.parse import unquote

from fastapi.testclient import TestClient

from app.main import app

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DOCUMENTS = [
    PROJECT_ROOT / name
    for name in (
        "API_EXAMPLES.md",
        "ARCHITECTURE.md",
        "CHANGELOG.md",
        "CODE_OF_CONDUCT.md",
        "CONTRIBUTING.md",
        "DATABASE_BENCHMARKS.md",
        "LOAD_TESTING.md",
        "DEPLOYMENT.md",
        "DEVELOPMENT.md",
        "MONITORING.md",
        "README.md",
        "RELEASE_CHECKLIST.md",
        "ROADMAP.md",
        "SECURITY.md",
    )
]
DOCUMENTS.append(PROJECT_ROOT / "docs" / "decisions" / "0001-keep-sync-sqlalchemy.md")
MARKDOWN_LINK = re.compile(r"(?<!!)\[[^]]+\]\(([^)]+)\)")
DOCUMENTED_API_PATHS = {
    "/admin/users",
    "/admin/users/{user_id}/role",
    "/auth/logout",
    "/auth/email-verification/confirm",
    "/auth/email-verification/request",
    "/auth/me",
    "/auth/mfa/challenge/verify",
    "/auth/mfa/disable",
    "/auth/mfa/recovery-codes/regenerate",
    "/auth/mfa/status",
    "/auth/mfa/totp/confirm",
    "/auth/mfa/totp/enroll",
    "/auth/oidc/authorize",
    "/auth/oidc/callback",
    "/auth/oidc/identities",
    "/auth/oidc/identities/{identity_id}",
    "/auth/oidc/link/authorize",
    "/auth/password-reset/confirm",
    "/auth/password-reset/request",
    "/auth/refresh",
    "/auth/sessions",
    "/auth/sessions/{session_id}",
    "/health/live",
    "/health/ready",
    "/login/",
    "/metrics",
    "/register/",
}
OPENAPI_API_PATHS = DOCUMENTED_API_PATHS - {"/metrics"}


def local_link_targets(document: Path):
    for match in MARKDOWN_LINK.finditer(document.read_text(encoding="utf-8")):
        destination = match.group(1).strip()
        if destination.startswith(("#", "http://", "https://", "mailto:")):
            continue

        path_text = unquote(destination.split("#", 1)[0])
        if path_text:
            yield (document.parent / path_text).resolve()


def test_documentation_links_resolve_to_files():
    missing = []

    for document in DOCUMENTS:
        assert document.is_file(), f"Missing documentation file: {document.name}"
        for target in local_link_targets(document):
            if not target.is_file():
                missing.append(f"{document.name} -> {target.name}")

    assert not missing, "Broken documentation links:\n" + "\n".join(missing)


def test_readme_indexes_the_task_guides():
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")

    for guide in (
        "API_EXAMPLES.md",
        "ARCHITECTURE.md",
        "DATABASE_BENCHMARKS.md",
        "LOAD_TESTING.md",
        "DEPLOYMENT.md",
        "DEVELOPMENT.md",
        "MONITORING.md",
    ):
        assert f"]({guide})" in readme


def test_documented_application_routes_exist_in_openapi_schema():
    openapi_paths = set(app.openapi()["paths"])

    assert OPENAPI_API_PATHS <= openapi_paths
    assert "/metrics" not in openapi_paths


def test_hidden_documented_metrics_endpoint_is_reachable():
    response = TestClient(app).get("/metrics")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
