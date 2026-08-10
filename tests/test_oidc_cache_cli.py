from app.commands.oidc_cache import build_parser, run_invalidation
from app.core.config import settings


class FakeCache:
    def __init__(self, result):
        self.result = result

    def invalidate(self):
        return self.result


def test_cache_cli_parser_accepts_scoped_invalidation():
    assert build_parser().parse_args(["invalidate-oidc"]).operation == "invalidate-oidc"


def test_cache_invalidation_requires_redis_mode(monkeypatch):
    monkeypatch.setattr(settings, "OIDC_CACHE_BACKEND", "none")
    assert run_invalidation(FakeCache(2)) == 2


def test_cache_invalidation_reports_success_and_failure(monkeypatch):
    monkeypatch.setattr(settings, "OIDC_CACHE_BACKEND", "redis")
    assert run_invalidation(FakeCache(2)) == 0
    assert run_invalidation(FakeCache(None)) == 1
