from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
KUBERNETES_DIR = PROJECT_ROOT / "deploy" / "kubernetes"


def test_kustomize_base_includes_the_required_runtime_resources():
    manifest = (KUBERNETES_DIR / "kustomization.yaml").read_text(encoding="utf-8")

    for name in (
        "deployment.yaml",
        "service.yaml",
        "hpa.yaml",
        "pdb.yaml",
        "networkpolicy.yaml",
    ):
        assert name in manifest


def test_deployment_uses_non_root_security_and_health_boundaries():
    manifest = (KUBERNETES_DIR / "deployment.yaml").read_text(encoding="utf-8")

    assert "readOnlyRootFilesystem: true" in manifest
    assert "allowPrivilegeEscalation: false" in manifest
    assert 'drop: ["ALL"]' in manifest
    assert "path: /health/live" in manifest
    assert "path: /health/ready" in manifest


def test_secret_template_is_not_a_kubernetes_secret_manifest():
    template = (KUBERNETES_DIR / "secret.example.env").read_text(encoding="utf-8")

    assert "SECRET_KEY=replace-with" in template
    assert "kind: Secret" not in template
