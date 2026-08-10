"""Reproducible synchronous SQLAlchemy database benchmark harness.

The benchmark uses a dedicated PostgreSQL schema named ``benchmark``. ORM
tables are redirected into that schema through ``schema_translate_map`` so
benchmark fixtures never touch the application's normal ``public`` tables.

The harness creates only the tables required by its workloads, uses bounded
fixtures, reports machine-readable JSON, and removes fixture rows after every
run.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import threading
import time
from collections import Counter
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

from sqlalchemy import create_engine, event, inspect, text, update
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.services.sessions import list_active_sessions

BENCHMARK_SCHEMA = "benchmark"
EXPECTED_TABLES = frozenset({"users", "refresh_tokens"})

SCENARIOS = (
    "user-read",
    "session-list",
    "refresh-lock",
    "session-revoke",
    "mixed",
)

MIXED_SCENARIOS = (
    "user-read",
    "session-list",
    "refresh-lock",
    "session-revoke",
)


class BenchmarkError(RuntimeError):
    """Raised when benchmark execution would be invalid or unsafe."""


@dataclass(frozen=True)
class BenchmarkFixture:
    user_id: int
    username: str
    refresh_token: str


@dataclass
class WorkerResult:
    latencies_ms: list[float]
    errors: Counter[str]


@dataclass(frozen=True)
class PoolSnapshot:
    size: int | None
    checked_in: int | None
    checked_out: int | None
    overflow: int | None


@dataclass(frozen=True)
class BenchmarkResult:
    schema_version: int
    implementation: str
    scenario: str
    concurrency: int
    duration_seconds: float
    warmup_seconds: float
    fixture_sessions: int
    operations: int
    errors: int
    error_rate: float
    throughput_per_second: float
    latency_ms_median: float | None
    latency_ms_p95: float | None
    latency_ms_p99: float | None
    query_count: int
    queries_per_operation: float
    pool_before: PoolSnapshot
    pool_after: PoolSnapshot
    database_backend: str
    database_driver: str | None
    database_name: str | None
    benchmark_schema: str
    python_pid: int
    error_types: dict[str, int]


def build_benchmark_engine() -> Engine:
    url = make_url(settings.DATABASE_URL)

    if url.get_backend_name() != "postgresql":
        raise BenchmarkError(
            "Database benchmarks require PostgreSQL so synchronous and async "
            "results can later be compared under equivalent conditions."
        )

    connect_args = {"options": "-c timezone=UTC"}

    engine = create_engine(
        url,
        connect_args=connect_args,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
        pool_timeout=30,
        pool_recycle=1800,
        execution_options={
            "schema_translate_map": {
                None: BENCHMARK_SCHEMA,
            }
        },
    )

    return engine


benchmark_engine = build_benchmark_engine()

BenchmarkSession = sessionmaker(
    bind=benchmark_engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
)


_query_count = 0
_query_count_lock = threading.Lock()


def _count_query(
    conn: Any,
    cursor: Any,
    statement: str,
    parameters: Any,
    context: Any,
    executemany: bool,
) -> None:
    del conn, cursor, statement, parameters, context, executemany

    global _query_count

    with _query_count_lock:
        _query_count += 1


def reset_query_count() -> None:
    global _query_count

    with _query_count_lock:
        _query_count = 0


def read_query_count() -> int:
    with _query_count_lock:
        return _query_count


def ensure_benchmark_schema() -> None:
    """Create and validate the dedicated benchmark schema."""

    with benchmark_engine.connect() as connection:
        database = connection.execute(text("SELECT current_database()")).scalar_one()

        current_schema = connection.execute(
            text("SELECT current_schema()")
        ).scalar_one()

        if current_schema == BENCHMARK_SCHEMA:
            raise BenchmarkError(
                "The benchmark connection unexpectedly uses the benchmark "
                "schema as its default schema."
            )

        connection.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{BENCHMARK_SCHEMA}"'))
        connection.commit()

    inspector = inspect(benchmark_engine)
    existing_tables = set(inspector.get_table_names(schema=BENCHMARK_SCHEMA))

    unexpected_tables = existing_tables - EXPECTED_TABLES

    if unexpected_tables:
        names = ", ".join(sorted(unexpected_tables))
        raise BenchmarkError(
            "Refusing to use benchmark schema because it contains unexpected "
            f"tables: {names}. Database: {database!r}."
        )


def ensure_benchmark_tables() -> None:
    """Create only tables required by the benchmark workloads."""

    User.__table__.create(
        bind=benchmark_engine,
        checkfirst=True,
    )

    RefreshToken.__table__.create(
        bind=benchmark_engine,
        checkfirst=True,
    )


def verify_schema_isolation() -> None:
    """Prove benchmark ORM statements resolve into the benchmark schema."""

    with BenchmarkSession() as db:
        translated_user_table = db.execute(
            text(
                """
                SELECT to_regclass(:table_name)
                """
            ),
            {"table_name": (f"{BENCHMARK_SCHEMA}.{User.__tablename__}")},
        ).scalar_one()

        translated_refresh_table = db.execute(
            text(
                """
                SELECT to_regclass(:table_name)
                """
            ),
            {"table_name": (f"{BENCHMARK_SCHEMA}.{RefreshToken.__tablename__}")},
        ).scalar_one()

    if translated_user_table is None or translated_refresh_table is None:
        raise BenchmarkError("Benchmark schema tables were not created successfully.")


def pool_snapshot() -> PoolSnapshot:
    pool = benchmark_engine.pool

    def read_metric(name: str) -> int | None:
        metric = getattr(pool, name, None)

        if metric is None:
            return None

        try:
            return int(metric())
        except (TypeError, ValueError):
            return None

    return PoolSnapshot(
        size=read_metric("size"),
        checked_in=read_metric("checkedin"),
        checked_out=read_metric("checkedout"),
        overflow=read_metric("overflow"),
    )


def create_fixture(session_count: int) -> BenchmarkFixture:
    username = f"benchmark-{uuid4().hex}"

    user = User(
        username=username,
        email=None,
        password="benchmark-only-not-for-authentication",
    )

    with BenchmarkSession() as db:
        try:
            db.add(user)
            db.flush()

            first_token = ""
            now = datetime.now(UTC)

            for index in range(session_count):
                token = f"benchmark-{uuid4().hex}"

                if index == 0:
                    first_token = token

                db.add(
                    RefreshToken(
                        user_id=user.id,
                        family_id=str(uuid4()),
                        token=token,
                        expires_at=now + timedelta(days=1),
                        device_name=f"Benchmark device {index}",
                    )
                )

            db.commit()

            return BenchmarkFixture(
                user_id=user.id,
                username=username,
                refresh_token=first_token,
            )
        except Exception:
            db.rollback()
            raise


def remove_fixture(fixture: BenchmarkFixture) -> None:
    with BenchmarkSession() as db:
        try:
            db.query(RefreshToken).filter(
                RefreshToken.user_id == fixture.user_id
            ).delete(synchronize_session=False)

            db.query(User).filter(User.id == fixture.user_id).delete(
                synchronize_session=False
            )

            db.commit()
        except Exception:
            db.rollback()
            raise


def scenario_user_read(fixture: BenchmarkFixture) -> None:
    with BenchmarkSession() as db:
        user = db.query(User).filter(User.username == fixture.username).first()

        if user is None:
            raise BenchmarkError("Benchmark user disappeared during execution.")


def scenario_session_list(fixture: BenchmarkFixture) -> None:
    with BenchmarkSession() as db:
        sessions = list_active_sessions(
            fixture.user_id,
            db,
        )

        if not sessions:
            raise BenchmarkError(
                "Benchmark session fixture disappeared during execution."
            )


def scenario_refresh_lock(fixture: BenchmarkFixture) -> None:
    with BenchmarkSession() as db:
        try:
            token = (
                db.query(RefreshToken)
                .filter(RefreshToken.token == fixture.refresh_token)
                .with_for_update()
                .first()
            )

            if token is None:
                raise BenchmarkError(
                    "Benchmark refresh token disappeared during execution."
                )
        finally:
            db.rollback()


def scenario_session_revoke(fixture: BenchmarkFixture) -> None:
    with BenchmarkSession() as db:
        try:
            db.execute(
                update(RefreshToken)
                .where(
                    RefreshToken.user_id == fixture.user_id,
                    RefreshToken.revoked.is_(False),
                )
                .values(
                    revoked=True,
                    revoked_at=datetime.now(UTC),
                    revocation_reason="benchmark",
                )
            )

            # Roll back deliberately so each measured operation starts from
            # an equivalent fixture state.
            db.rollback()
        except Exception:
            db.rollback()
            raise


def scenario_for_name(
    name: str,
) -> Callable[[BenchmarkFixture], None]:
    scenarios: dict[str, Callable[[BenchmarkFixture], None]] = {
        "user-read": scenario_user_read,
        "session-list": scenario_session_list,
        "refresh-lock": scenario_refresh_lock,
        "session-revoke": scenario_session_revoke,
    }

    try:
        return scenarios[name]
    except KeyError as error:
        raise BenchmarkError(f"Unknown benchmark scenario: {name}") from error


def run_operation(
    scenario: str,
    fixture: BenchmarkFixture,
    operation_index: int,
) -> None:
    selected = scenario

    if scenario == "mixed":
        selected = MIXED_SCENARIOS[operation_index % len(MIXED_SCENARIOS)]

    scenario_for_name(selected)(fixture)


def run_worker(
    *,
    scenario: str,
    fixture: BenchmarkFixture,
    deadline: float,
    worker_index: int,
    record_latency: bool,
) -> WorkerResult:
    latencies_ms: list[float] = []
    errors: Counter[str] = Counter()
    operation_index = worker_index

    while time.perf_counter() < deadline:
        started = time.perf_counter()

        try:
            run_operation(
                scenario,
                fixture,
                operation_index,
            )
        except Exception as error:
            errors[type(error).__name__] += 1
        else:
            if record_latency:
                latencies_ms.append((time.perf_counter() - started) * 1000)

        operation_index += 1

    return WorkerResult(
        latencies_ms=latencies_ms,
        errors=errors,
    )


def run_phase(
    *,
    scenario: str,
    fixture: BenchmarkFixture,
    concurrency: int,
    seconds: float,
    record_latency: bool,
) -> list[WorkerResult]:
    if seconds <= 0:
        return []

    deadline = time.perf_counter() + seconds

    with ThreadPoolExecutor(
        max_workers=concurrency,
        thread_name_prefix="db-benchmark",
    ) as executor:
        futures = [
            executor.submit(
                run_worker,
                scenario=scenario,
                fixture=fixture,
                deadline=deadline,
                worker_index=index,
                record_latency=record_latency,
            )
            for index in range(concurrency)
        ]

        return [future.result() for future in futures]


def percentile(
    values: list[float],
    fraction: float,
) -> float | None:
    if not values:
        return None

    ordered = sorted(values)

    if len(ordered) == 1:
        return ordered[0]

    position = (len(ordered) - 1) * fraction
    lower_index = int(position)
    upper_index = min(
        lower_index + 1,
        len(ordered) - 1,
    )
    weight = position - lower_index

    return ordered[lower_index] * (1 - weight) + ordered[upper_index] * weight


def rounded(
    value: float | None,
) -> float | None:
    if value is None:
        return None

    return round(value, 3)


def build_result(
    *,
    scenario: str,
    concurrency: int,
    duration: float,
    warmup: float,
    fixture_sessions: int,
    worker_results: list[WorkerResult],
    query_count: int,
    pool_before: PoolSnapshot,
    pool_after: PoolSnapshot,
) -> BenchmarkResult:
    latencies = [
        latency for result in worker_results for latency in result.latencies_ms
    ]

    error_types: Counter[str] = Counter()

    for result in worker_results:
        error_types.update(result.errors)

    operations = len(latencies)
    errors = sum(error_types.values())
    attempts = operations + errors

    measured_duration = max(
        duration,
        0.000001,
    )

    url = make_url(settings.DATABASE_URL)

    return BenchmarkResult(
        schema_version=1,
        implementation="sync-sqlalchemy",
        scenario=scenario,
        concurrency=concurrency,
        duration_seconds=round(duration, 6),
        warmup_seconds=warmup,
        fixture_sessions=fixture_sessions,
        operations=operations,
        errors=errors,
        error_rate=(round(errors / attempts, 6) if attempts else 0.0),
        throughput_per_second=round(
            operations / measured_duration,
            3,
        ),
        latency_ms_median=rounded(statistics.median(latencies) if latencies else None),
        latency_ms_p95=rounded(percentile(latencies, 0.95)),
        latency_ms_p99=rounded(percentile(latencies, 0.99)),
        query_count=query_count,
        queries_per_operation=(
            round(
                query_count / operations,
                3,
            )
            if operations
            else 0.0
        ),
        pool_before=pool_before,
        pool_after=pool_after,
        database_backend=url.get_backend_name(),
        database_driver=url.get_driver_name(),
        database_name=url.database,
        benchmark_schema=BENCHMARK_SCHEMA,
        python_pid=os.getpid(),
        error_types=dict(sorted(error_types.items())),
    )


def run_benchmark(
    args: argparse.Namespace,
) -> BenchmarkResult:
    ensure_benchmark_schema()
    ensure_benchmark_tables()
    verify_schema_isolation()

    fixture = create_fixture(args.fixture_sessions)

    try:
        if args.warmup > 0:
            run_phase(
                scenario=args.scenario,
                fixture=fixture,
                concurrency=args.concurrency,
                seconds=args.warmup,
                record_latency=False,
            )

        pool_before = pool_snapshot()
        reset_query_count()

        measured_started = time.perf_counter()

        results = run_phase(
            scenario=args.scenario,
            fixture=fixture,
            concurrency=args.concurrency,
            seconds=args.duration,
            record_latency=True,
        )

        measured_duration = time.perf_counter() - measured_started

        query_count = read_query_count()
        pool_after = pool_snapshot()

        return build_result(
            scenario=args.scenario,
            concurrency=args.concurrency,
            duration=measured_duration,
            warmup=args.warmup,
            fixture_sessions=args.fixture_sessions,
            worker_results=results,
            query_count=query_count,
            pool_before=pool_before,
            pool_after=pool_after,
        )
    finally:
        remove_fixture(fixture)


def write_result(
    result: BenchmarkResult,
    output: Path | None,
) -> None:
    payload = json.dumps(
        asdict(result),
        indent=2,
        sort_keys=True,
    )

    print(payload)

    if output is not None:
        output.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        output.write_text(
            payload + "\n",
            encoding="utf-8",
        )


def positive_int(value: str) -> int:
    parsed = int(value)

    if parsed <= 0:
        raise argparse.ArgumentTypeError("value must be greater than zero")

    return parsed


def non_negative_float(value: str) -> float:
    parsed = float(value)

    if parsed < 0:
        raise argparse.ArgumentTypeError("value must be greater than or equal to zero")

    return parsed


def positive_float(value: str) -> float:
    parsed = float(value)

    if parsed <= 0:
        raise argparse.ArgumentTypeError("value must be greater than zero")

    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Benchmark representative synchronous SQLAlchemy/PostgreSQL "
            "database workloads inside an isolated benchmark schema."
        )
    )

    parser.add_argument(
        "--scenario",
        choices=SCENARIOS,
        default="user-read",
        help="Database workload to measure.",
    )

    parser.add_argument(
        "--concurrency",
        type=positive_int,
        default=4,
        help="Number of concurrent benchmark worker threads.",
    )

    parser.add_argument(
        "--duration",
        type=positive_float,
        default=10.0,
        help="Measured benchmark duration in seconds.",
    )

    parser.add_argument(
        "--warmup",
        type=non_negative_float,
        default=2.0,
        help="Warm-up duration in seconds before measurements begin.",
    )

    parser.add_argument(
        "--fixture-sessions",
        type=positive_int,
        default=50,
        help="Number of refresh-token rows created for the benchmark user.",
    )

    parser.add_argument(
        "--output",
        type=Path,
        help="Optional path for machine-readable JSON results.",
    )

    return parser


def main(
    argv: list[str] | None = None,
) -> int:
    args = build_parser().parse_args(argv)

    event.listen(
        benchmark_engine,
        "before_cursor_execute",
        _count_query,
    )

    try:
        result = run_benchmark(args)
        write_result(
            result,
            args.output,
        )
    except BenchmarkError as error:
        print(
            f"Error: {error}",
            file=os.sys.stderr,
        )
        return 2
    except KeyboardInterrupt:
        print(
            "Benchmark interrupted.",
            file=os.sys.stderr,
        )
        return 130
    finally:
        event.remove(
            benchmark_engine,
            "before_cursor_execute",
            _count_query,
        )

        benchmark_engine.dispose()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
