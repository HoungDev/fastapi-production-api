# Database benchmark and async evaluation

This guide defines the reproducible database evaluation used for the v1.3
architecture decision. The production application remains synchronous. The
async implementation under `benchmarks/` is an isolated experiment and is not
imported by application startup or included as a console entry point.

## Decision

Keep synchronous SQLAlchemy for v1.3.0. The repository does not yet have
representative production measurements showing that an async migration would
justify its transaction, testing, debugging, and operational cost. The new
comparison harness makes that decision repeatable; a future dedicated migration
issue requires sustained evidence against a real workload before changing the
production path.

CI smoke timings are deliberately not treated as performance evidence. Shared
runners are noisy and the smoke workload is too short. The decision can be
revisited when five extended runs show a material, repeatable improvement at
the expected concurrency without increasing error rate or weakening existing
transaction semantics.

## What is measured

Both modes execute the same SQL and transaction boundaries against the same
fixture data and PostgreSQL instance.

| Scenario | Database behavior represented |
| --- | --- |
| `authenticated_read` | Indexed current-user lookup after token validation |
| `session_list` | Bounded device-session list through a compound index |
| `refresh_rotation` | Locked read and update in one rotation transaction |
| `write` | Representative bounded update transaction |
| `mixed` | Equal deterministic mix of the four database-bound scenarios |

The harness reports requests per second, median/p95/p99/min/max latency, error
rate and bounded error classes, connection acquisition time, checkout/checkin
counts, and peak checked-out connections. It does not record credentials,
queries containing user input, application tokens, or row contents.

The database-focused scenarios intentionally exclude bcrypt, JWT signing,
HTTP parsing, Redis latency, SMTP, and tracing export. Those costs should be
measured separately by the planned end-to-end load-testing work. This separation
prevents external dependency latency from being mistaken for a database-driver
effect.

## Safety model

The tool never implicitly uses `DATABASE_URL`. Set `BENCHMARK_DATABASE_URL` or
pass `--database-url`. It accepts only PostgreSQL on `localhost`, `127.0.0.1`,
`::1`, or the local Compose service name `postgres`, and the database name must
contain `test`, `bench`, `local`, or `dev`.

Fixtures live only in the `fastapi_benchmark` schema. `prepare` resets that
schema's two tables; `cleanup` drops only that schema. Never point the tool at a
shared or production database.

## Short local smoke run

Start and migrate the local services, then use the test database or create a
dedicated database whose name contains `benchmark`:

```bash
export BENCHMARK_DATABASE_URL='postgresql+psycopg://fastapi_user:fastapi_password@localhost:5432/fastapi_test'
uv run python -m benchmarks.db prepare --records 100
uv run python -m benchmarks.db run --mode both --scenarios authenticated_read refresh_rotation --iterations 20 --warmup 5 --concurrency 2 --pool-size 2 --output benchmark-smoke.json
uv run python -m benchmarks.db verify-async-rollback
uv run python -m benchmarks.db cleanup
```

PowerShell uses the same commands after setting:

```powershell
$env:BENCHMARK_DATABASE_URL='postgresql+psycopg://fastapi_user:fastapi_password@localhost:5432/fastapi_test'
```

CI runs this bounded smoke path and uploads `benchmark-smoke.json`. It verifies
imports, fixtures, both drivers, stable result structure, and async rollback;
it enforces no timing threshold.

## Extended comparison methodology

Record the following alongside every retained result artifact:

- commit SHA and unchanged `uv.lock`;
- Python 3.13 patch version, operating system, CPU model/count, and memory;
- PostgreSQL 17 patch version, configuration, and whether it is local;
- one application/benchmark process unless a worker comparison is explicit;
- identical `--pool-size` and `--max-overflow` for both modes;
- dataset size, scenario, concurrency, warm-up, iterations, and repetition;
- tracing disabled, log level, metrics mode, and Redis excluded from DB-only runs;
- CPU and resident-memory observations from the OS or container runtime;
- cold-start observations kept separate from steady-state results.

Recommended controlled run:

1. Use a dedicated local PostgreSQL 17 database on loopback with no competing
   workload and prepare at least 10,000 principals.
2. Keep pool size at 5 and overflow at 0 for both drivers.
3. For each concurrency in 1, 5, 10, 25, and 50, run all scenarios with 500
   warm-up operations and at least 10,000 measured operations.
4. Alternate sync-first and async-first ordering to reduce thermal/order bias.
5. Repeat the complete matrix five times. Retain raw JSON rather than only
   copied summary values.
6. Report the median of run-level throughput and latency percentiles plus the
   observed range. Investigate all errors and pool waits before comparing speed.

Example extended invocation for one matrix point:

```bash
uv run python -m benchmarks.db prepare --records 10000
uv run python -m benchmarks.db run --mode both --iterations 10000 --warmup 500 --concurrency 25 --pool-size 5 --max-overflow 0 --output results/c25-run1.json
uv run python -m benchmarks.db cleanup
```

## Interpretation and adoption gate

Throughput alone is insufficient. Compare p95/p99 latency, acquisition wait,
peak pool use, error rate, CPU, memory, and transaction correctness. Direct
equivalence ends above the driver/session layer: the synchronous production
stack can use multiple worker processes, while one async process multiplexes
database waits on an event loop. Any worker-level comparison must document that
difference rather than presenting it as a driver-only result.

Open a dedicated async-migration issue only if representative extended runs
show a repeatable improvement large enough to matter to the service SLO (a 20%
change is a useful review trigger, not a universal threshold), with equal error
rate, bounded connection pressure, passing rollback/security tests, and a clear
operational plan. Otherwise retain the simpler synchronous path or consider
async only for a narrowly isolated I/O-heavy component.

## Current comparison record

| Evidence | Sync | Async prototype | Architectural weight |
| --- | --- | --- | --- |
| CI PostgreSQL smoke | Required and artifacted | Required and artifacted | Correctness only |
| Transaction rollback | Existing production tests | Explicit rollback probe | Must pass |
| Production integration | Current maintained path | Not integrated | Favors sync |
| Representative extended measurements | Not yet supplied | Not yet supplied | No migration evidence |

The absence of representative measurements is recorded explicitly rather than
replaced with fabricated numbers. Under the issue's decision guardrails, that
evidence supports keeping sync for v1.3.0 and deferring any full migration.

