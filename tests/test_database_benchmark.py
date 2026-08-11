import asyncio

import pytest

from app.core.config import settings
from benchmarks.db import (
    BenchmarkSafetyError,
    PoolObserver,
    RunConfig,
    Sample,
    async_url,
    cleanup_fixture,
    prepare_fixture,
    run_async,
    run_sync,
    summarize,
    sync_url,
    validate_benchmark_url,
    verify_async_rollback,
)


def test_benchmark_url_is_fail_closed():
    with pytest.raises(BenchmarkSafetyError, match="PostgreSQL"):
        validate_benchmark_url("sqlite:///benchmark.db")
    with pytest.raises(BenchmarkSafetyError, match="non-local"):
        validate_benchmark_url(
            "postgresql://user:password@database.example.com/app_test"
        )
    with pytest.raises(BenchmarkSafetyError, match="Database name"):
        validate_benchmark_url("postgresql://user:password@localhost/production")


def test_benchmark_url_selects_explicit_drivers_without_exposing_credentials():
    value = "postgresql://user:password@localhost/app_test"

    assert sync_url(value).drivername == "postgresql+psycopg"
    assert async_url(value).drivername == "postgresql+asyncpg"


def test_summary_schema_is_stable_and_counts_errors():
    observer = PoolObserver()
    observer.checkout()
    observer.checkin()

    result = summarize(
        mode="sync",
        scenario="authenticated_read",
        samples=[
            Sample(latency_ms=10, pool_wait_ms=1),
            Sample(latency_ms=20, pool_wait_ms=2),
            Sample(latency_ms=30, pool_wait_ms=0, error="DatabaseError"),
        ],
        duration=1,
        observer=observer,
    )

    assert result == {
        "mode": "sync",
        "scenario": "authenticated_read",
        "attempts": 3,
        "successes": 2,
        "errors": 1,
        "error_rate": 0.333333,
        "error_types": {"DatabaseError": 1},
        "duration_seconds": 1,
        "throughput_rps": 2.0,
        "latency_ms": {
            "minimum": 10,
            "median": 15.0,
            "p95": 19.5,
            "p99": 19.9,
            "maximum": 20,
        },
        "pool_wait_ms": {
            "minimum": 1,
            "median": 1.5,
            "p95": 1.95,
            "p99": 1.99,
            "maximum": 2,
        },
        "pool": {"checkouts": 1, "checkins": 1, "peak_in_use": 1},
    }


def test_sync_and_async_prototypes_run_against_isolated_postgres():
    database_url = settings.DATABASE_URL
    config = RunConfig(
        iterations=8,
        warmup=2,
        concurrency=2,
        pool_size=2,
        max_overflow=0,
    )
    prepare_fixture(database_url, records=20)
    try:
        sync_result = run_sync(database_url, "authenticated_read", config)
        async_result = asyncio.run(
            run_async(database_url, "authenticated_read", config)
        )

        assert sync_result["successes"] == config.iterations
        assert async_result["successes"] == config.iterations
        assert sync_result["errors"] == async_result["errors"] == 0
        assert asyncio.run(verify_async_rollback(database_url)) is True
    finally:
        cleanup_fixture(database_url)
