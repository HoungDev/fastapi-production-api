import asyncio
import os
import selectors
from collections import Counter
from dataclasses import asdict

import pytest

from scripts.benchmarks import async_db_benchmark, db_benchmark


@pytest.mark.parametrize(
    ("values", "fraction", "expected"),
    [
        ([], 0.95, None),
        ([5.0], 0.95, 5.0),
        ([1.0, 2.0, 3.0, 4.0], 0.5, 2.5),
        ([1.0, 2.0, 3.0, 4.0], 0.95, 3.85),
        ([4.0, 1.0, 3.0, 2.0], 0.99, 3.97),
    ],
)
def test_sync_percentile(values, fraction, expected):
    assert db_benchmark.percentile(values, fraction) == pytest.approx(expected)


@pytest.mark.parametrize(
    ("values", "fraction", "expected"),
    [
        ([], 0.95, None),
        ([5.0], 0.95, 5.0),
        ([1.0, 2.0, 3.0, 4.0], 0.5, 2.5),
        ([1.0, 2.0, 3.0, 4.0], 0.95, 3.85),
        ([4.0, 1.0, 3.0, 2.0], 0.99, 3.97),
    ],
)
def test_async_percentile(values, fraction, expected):
    assert async_db_benchmark.percentile(values, fraction) == pytest.approx(expected)


@pytest.mark.parametrize(
    "module",
    [
        db_benchmark,
        async_db_benchmark,
    ],
)
def test_numeric_argument_validation(module):
    assert module.positive_int("3") == 3
    assert module.non_negative_float("0") == 0.0
    assert module.positive_float("1.5") == 1.5

    with pytest.raises(Exception):
        module.positive_int("0")

    with pytest.raises(Exception):
        module.non_negative_float("-1")

    with pytest.raises(Exception):
        module.positive_float("0")


def _worker_results(module):
    return [
        module.WorkerResult(
            latencies_ms=[1.0, 2.0],
            errors=Counter(),
        ),
        module.WorkerResult(
            latencies_ms=[3.0, 4.0],
            errors=Counter({"RuntimeError": 1}),
        ),
    ]


def _pool_snapshot(module):
    return module.PoolSnapshot(
        size=5,
        checked_in=4,
        checked_out=1,
        overflow=0,
    )


def _build_result(module):
    pool = _pool_snapshot(module)

    return module.build_result(
        scenario="user-read",
        concurrency=2,
        duration=2.0,
        warmup=1.0,
        fixture_sessions=5,
        worker_results=_worker_results(module),
        query_count=8,
        pool_before=pool,
        pool_after=pool,
    )


def test_sync_result_metrics():
    result = _build_result(db_benchmark)

    assert result.schema_version == 1
    assert result.implementation == "sync-sqlalchemy"
    assert result.scenario == "user-read"
    assert result.operations == 4
    assert result.errors == 1
    assert result.error_rate == 0.2
    assert result.throughput_per_second == 2.0
    assert result.latency_ms_median == 2.5
    assert result.latency_ms_p95 == 3.85
    assert result.latency_ms_p99 == 3.97
    assert result.query_count == 8
    assert result.queries_per_operation == 2.0
    assert result.benchmark_schema == "benchmark"
    assert result.error_types == {"RuntimeError": 1}


def test_async_result_metrics():
    result = _build_result(async_db_benchmark)

    assert result.schema_version == 1
    assert result.implementation == "async-sqlalchemy-psycopg"
    assert result.scenario == "user-read"
    assert result.operations == 4
    assert result.errors == 1
    assert result.error_rate == 0.2
    assert result.throughput_per_second == 2.0
    assert result.latency_ms_median == 2.5
    assert result.latency_ms_p95 == 3.85
    assert result.latency_ms_p99 == 3.97
    assert result.query_count == 8
    assert result.queries_per_operation == 2.0
    assert result.benchmark_schema == "benchmark"
    assert result.error_types == {"RuntimeError": 1}


def test_sync_and_async_results_use_same_schema():
    sync_result = asdict(_build_result(db_benchmark))
    async_result = asdict(_build_result(async_db_benchmark))

    assert sync_result.keys() == async_result.keys()
    assert sync_result["schema_version"] == async_result["schema_version"] == 1


def test_sync_benchmark_postgresql_smoke_and_rollback():
    db_benchmark.ensure_benchmark_schema()
    db_benchmark.ensure_benchmark_tables()
    db_benchmark.verify_schema_isolation()

    fixture = db_benchmark.create_fixture(2)

    try:
        db_benchmark.scenario_user_read(fixture)

        # This scenario performs an UPDATE and deliberately rolls it back.
        db_benchmark.scenario_session_revoke(fixture)

        # If the rollback failed, no active sessions would remain and this
        # scenario would raise BenchmarkError.
        db_benchmark.scenario_session_list(fixture)
    finally:
        try:
            db_benchmark.remove_fixture(fixture)
        finally:
            db_benchmark.benchmark_engine.dispose()


async def _exercise_async_benchmark():
    fixture = None

    try:
        await async_db_benchmark.ensure_benchmark_schema()
        await async_db_benchmark.ensure_benchmark_tables()
        await async_db_benchmark.verify_schema_isolation()

        fixture = await async_db_benchmark.create_fixture(2)

        await async_db_benchmark.scenario_user_read(fixture)

        # This scenario performs an UPDATE and deliberately rolls it back.
        await async_db_benchmark.scenario_session_revoke(fixture)

        # Successful listing proves that the revoked state was not committed.
        await async_db_benchmark.scenario_session_list(fixture)
    finally:
        try:
            if fixture is not None:
                await async_db_benchmark.remove_fixture(fixture)
        finally:
            await async_db_benchmark.benchmark_engine.dispose()


def test_async_benchmark_postgresql_connectivity_and_rollback():
    coroutine = _exercise_async_benchmark()

    if os.name == "nt":
        asyncio.run(
            coroutine,
            loop_factory=lambda: asyncio.SelectorEventLoop(selectors.SelectSelector()),
        )
        return

    asyncio.run(coroutine)
