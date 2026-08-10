# Database Performance Evaluation

This document records the database-performance evaluation for Issue #44 and
the architectural decision on whether the application should migrate from
synchronous SQLAlchemy to async SQLAlchemy for v1.3.0.

## Decision

**Keep synchronous SQLAlchemy as the production database architecture for
v1.3.0.**

The measured async SQLAlchemy prototype did not provide a consistent performance
advantage over the existing synchronous implementation across the tested
workloads and concurrency levels.

Synchronous SQLAlchemy produced higher throughput in every measured
sync-versus-async comparison. Async median and tail latency were also generally
higher. One low-concurrency `mixed` measurement produced modestly lower async
p95 and p99 latency, but async throughput and median latency were worse in that
same run and the tail-latency advantage did not persist at higher concurrency.

The async prototype remains an evaluation artifact only. Production database
sessions, transaction boundaries, API behavior, migrations, authentication,
authorization, refresh-token rotation, and outbox behavior remain unchanged.

A future async migration should be considered only if the application's real
workload changes enough to justify a new benchmark and the measured benefit
outweighs the additional implementation and operational complexity.

## Goals

The evaluation was designed to answer the following questions:

1. What is the current synchronous SQLAlchemy/PostgreSQL performance baseline?
2. Where does the current implementation begin to saturate as concurrency
   increases?
3. Does SQLAlchemy async improve throughput or latency under equivalent
   workloads?
4. Does async materially improve the database-bound workloads that are most
   expensive in the current application?
5. Is a production migration to async SQLAlchemy justified by measured data?

The evaluation intentionally did not assume that async would be faster.

## Environment

The recorded measurements were produced on a local development workstation.

### Application/runtime

- Python 3.13
- SQLAlchemy 2.x
- Psycopg 3
- PostgreSQL backend
- synchronous driver: Psycopg
- async driver: Psycopg async support through `postgresql+psycopg`
- no additional `asyncpg` dependency was required

### Database

- PostgreSQL 17.10
- native PostgreSQL service on Windows
- database: `fastapi_db`
- dedicated benchmark schema: `benchmark`

The benchmark schema is isolated from the application's normal `public`
schema.

### Host

- Windows
- Intel Core i5-10400 CPU

These results describe this benchmark environment and must not be interpreted
as universal production capacity numbers.

## Connection-pool configuration

The synchronous and async implementations were configured with equivalent
pool limits:

```text
pool_size=5
max_overflow=10
pool_timeout=30
pool_recycle=1800
pool_pre_ping=True
```

This gives both implementations the same nominal database-connection budget.

## Benchmark isolation

The benchmark tooling uses a dedicated PostgreSQL schema:

```text
benchmark
```

SQLAlchemy's `schema_translate_map` redirects ORM tables into this schema.

The benchmark currently creates only the tables required for its workloads:

```text
benchmark.users
benchmark.refresh_tokens
```

The application tables in `public` are not used for benchmark fixtures.

A smoke test confirmed cleanup and isolation after execution:

```text
BENCHMARK_USERS_LEFT=0
BENCHMARK_TOKENS_LEFT=0
PUBLIC_BENCHMARK_USERS=0
PUBLIC_BENCHMARK_TOKENS=0
```

This means benchmark fixture rows were removed and no benchmark rows were
written into the application's normal `public` tables.

## Benchmark methodology

Unless otherwise noted, the comparison used:

- warm-up: 2 seconds
- measured duration: 10 seconds
- fixture refresh-token rows: 50
- concurrency levels: 1, 4, 8, and 16
- identical PostgreSQL instance
- identical database schema
- equivalent connection-pool limits
- equivalent query shapes
- equivalent transaction behavior
- identical fixture sizes
- one process per benchmark invocation

Each result records:

- operations per second
- median latency
- p95 latency
- p99 latency
- errors
- error rate
- database query count
- queries per successful operation
- connection-pool snapshot before and after measurement

No timing threshold is intended for normal GitHub-hosted CI because shared
runner performance is too noisy for reliable regression enforcement.

## Workloads

### `user-read`

Representative indexed user lookup.

Characteristics:

- read-only
- one database query per operation
- minimal application-side processing

### `session-list`

Representative session/device listing.

Characteristics:

- reads refresh-token records for a user
- one database query per operation
- groups session families in Python
- filters expired/revoked records
- represents combined database and application-side processing

### `refresh-lock`

Representative pessimistic-lock workload.

Characteristics:

- refresh-token lookup
- `SELECT ... FOR UPDATE`
- transaction rollback after measurement
- preserves the locking shape used by refresh-token workflows

### `session-revoke`

Representative write transaction.

Characteristics:

- bulk `UPDATE`
- changes refresh-token revocation state
- rollback after each benchmark operation so every operation starts from an
  equivalent fixture state

### `mixed`

Round-robin combination of:

- `user-read`
- `session-list`
- `refresh-lock`
- `session-revoke`

## Synchronous baseline

### User read

| Concurrency | Ops/s | Median ms | P95 ms | P99 ms | Errors |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 1055.353 | 0.889 | 1.132 | 2.124 | 0 |
| 4 | 1352.519 | 2.846 | 3.802 | 6.465 | 0 |
| 8 | 1289.737 | 5.963 | 8.537 | 12.623 | 0 |
| 16 | 1267.848 | 11.357 | 16.617 | 20.643 | 0 |

The highest throughput occurred at concurrency 4.

Increasing concurrency from 4 to 8 and 16 did not improve throughput and
substantially increased latency.

### Session revoke

| Concurrency | Ops/s | Median ms | P95 ms | P99 ms | Errors |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 414.283 | 2.335 | 2.695 | 5.318 | 0 |
| 4 | 638.362 | 5.984 | 7.940 | 12.036 | 0 |
| 8 | 580.827 | 13.753 | 17.369 | 21.229 | 0 |
| 16 | 505.092 | 28.657 | 36.421 | 41.662 | 0 |

Again, concurrency 4 produced the highest throughput.

From concurrency 4 to 16, throughput fell while median latency increased by
approximately 4.8 times.

### Session list

| Concurrency | Ops/s | Median ms | P95 ms | P99 ms | Errors |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 562.264 | 1.714 | 2.258 | 3.403 | 0 |
| 4 | 692.709 | 5.580 | 7.818 | 11.650 | 0 |
| 8 | 621.365 | 12.613 | 17.833 | 20.882 | 0 |
| 16 | 614.052 | 23.776 | 33.207 | 38.031 | 0 |

Concurrency 4 again produced the best throughput.

### Cross-workload synchronous result at concurrency 4

| Scenario | Ops/s | Median ms | P95 ms | P99 ms | Errors |
| --- | ---: | ---: | ---: | ---: | ---: |
| `user-read` | 1352.519 | 2.846 | 3.802 | 6.465 | 0 |
| `refresh-lock` | 1188.766 | 3.167 | 4.638 | 7.932 | 0 |
| `mixed` | 990.693 | 3.868 | 5.966 | 9.377 | 0 |
| `session-list` | 692.709 | 5.580 | 7.818 | 11.650 | 0 |
| `session-revoke` | 638.362 | 5.984 | 7.940 | 12.036 | 0 |

The heaviest measured workloads were `session-revoke` and `session-list`.

All measured synchronous workloads completed with zero benchmark errors.

## Async prototype

The async implementation uses:

```text
SQLAlchemy AsyncEngine
AsyncSession
postgresql+psycopg
asyncio workers
```

It does not replace the production database layer.

On Windows, Psycopg async requires a selector-compatible asyncio event loop
rather than the default Proactor event loop. The benchmark therefore uses a
`SelectorEventLoop` on Windows.

This platform-specific requirement is another operational consideration for
an async migration, although it is not by itself a reason to reject async.

## Sync versus async

### User read

### Refresh lock

| Concurrency | Sync ops/s | Async ops/s | Async throughput delta |
| ---: | ---: | ---: | ---: |
| 1 | 1047.587 | 801.340 | -23.5% |
| 4 | 1370.630 | 978.629 | -28.6% |
| 8 | 1308.266 | 947.756 | -27.6% |
| 16 | 1250.037 | 913.502 | -26.9% |

Latency comparison:

| Concurrency | Sync median ms | Async median ms | Sync P99 ms | Async P99 ms |
| ---: | ---: | ---: | ---: | ---: |
| 1 | 0.926 | 1.241 | 1.339 | 1.609 |
| 4 | 2.883 | 4.028 | 3.952 | 5.058 |
| 8 | 6.037 | 8.299 | 7.832 | 10.828 |
| 16 | 11.779 | 17.108 | 14.989 | 19.170 |

The synchronous implementation produced higher throughput and lower median and
p99 latency at every tested concurrency level for the pessimistic-lock
workload. Both implementations showed increasing latency as concurrency rose,
but the async prototype did not provide an advantage under the measured
contention pattern.

### Session revoke

| Concurrency | Sync ops/s | Async ops/s | Async throughput delta |
| ---: | ---: | ---: | ---: |
| 1 | 414.283 | 345.811 | -16.5% |
| 4 | 638.362 | 572.111 | -10.4% |
| 8 | 580.827 | 548.643 | -5.5% |
| 16 | 505.092 | 483.466 | -4.3% |

Latency comparison:

| Concurrency | Sync median ms | Async median ms | Sync P99 ms | Async P99 ms |
| ---: | ---: | ---: | ---: | ---: |
| 1 | 2.335 | 2.746 | 5.318 | 6.451 |
| 4 | 5.984 | 6.588 | 12.036 | 13.494 |
| 8 | 13.753 | 14.014 | 21.229 | 22.689 |
| 16 | 28.657 | 32.513 | 41.662 | 43.031 |

The throughput gap narrowed under higher contention, but async still did not
exceed sync.

### Session list

| Concurrency | Sync ops/s | Async ops/s | Async throughput delta |
| ---: | ---: | ---: | ---: |
| 1 | 562.264 | 497.920 | -11.4% |
| 4 | 692.709 | 580.463 | -16.2% |
| 8 | 621.365 | 572.770 | -7.8% |
| 16 | 614.052 | 533.589 | -13.1% |

Latency comparison:

| Concurrency | Sync median ms | Async median ms | Sync P99 ms | Async P99 ms |
| ---: | ---: | ---: | ---: | ---: |
| 1 | 1.714 | 1.915 | 3.403 | 4.912 |
| 4 | 5.580 | 6.516 | 11.650 | 15.195 |
| 8 | 12.613 | 12.927 | 20.882 | 34.293 |
| 16 | 23.776 | 28.549 | 38.031 | 53.910 |

Async again failed to provide a throughput or tail-latency advantage.

### Mixed workload

| Concurrency | Sync ops/s | Async ops/s | Async throughput delta |
| ---: | ---: | ---: | ---: |
| 1 | 655.479 | 600.281 | -8.4% |
| 4 | 1023.104 | 791.756 | -22.6% |
| 8 | 988.292 | 793.806 | -19.7% |
| 16 | 947.718 | 768.283 | -18.9% |

Latency comparison:

| Concurrency | Sync median ms | Async median ms | Sync P95 ms | Async P95 ms | Sync P99 ms | Async P99 ms |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 1.518 | 1.715 | 2.453 | 2.293 | 2.822 | 2.540 |
| 4 | 3.855 | 4.889 | 5.476 | 6.925 | 6.294 | 7.870 |
| 8 | 7.963 | 9.803 | 12.441 | 13.845 | 13.926 | 15.456 |
| 16 | 10.691 | 18.894 | 28.537 | 35.186 | 30.563 | 39.062 |

Synchronous SQLAlchemy produced higher throughput and lower median latency at
every tested concurrency level.

At concurrency 1, the async prototype produced modestly lower p95 and p99
latency despite having lower throughput and higher median latency. That
tail-latency advantage did not persist: at concurrency 4, 8, and 16, synchronous
SQLAlchemy produced both higher throughput and lower p95 and p99 latency.

The isolated low-concurrency tail-latency result is not sufficient evidence for
an async migration, but it is recorded explicitly so the architectural decision
does not overstate the benchmark findings.

## Saturation analysis

Across the measured workloads, concurrency 4 was generally the throughput
sweet spot.

At concurrency 8 and 16:

- throughput usually stopped improving or declined;
- median latency increased significantly;
- p95 and p99 latency increased significantly;
- error rates remained zero.

This pattern appeared in both synchronous and async implementations.

That result indicates the observed saturation is not simply caused by the use
of synchronous SQLAlchemy.

Likely contributors include:

- database transaction cost;
- connection-pool pressure;
- database-side concurrency;
- row/update contention;
- local PostgreSQL capacity;
- application-side object construction and processing.

Changing the Python database API from sync to async does not remove those
constraints.

## Architectural decision

The production application will remain on synchronous SQLAlchemy for v1.3.0.

### Reasons

1. **No measured throughput advantage**

   Async failed to outperform sync in throughput in every tested workload and
   concurrency level.

2. **No consistent latency advantage**

   Async median, p95, and p99 latency were generally higher. One
   low-concurrency mixed-workload run showed modestly lower async p95 and p99
   latency, but async throughput and median latency were worse in that same run,
   and the tail-latency advantage did not persist as concurrency increased.

3. **No evidence that async fixes saturation**

   Both implementations showed similar saturation patterns as concurrency
   increased.

4. **Current sync architecture is already explicit**

   The production database engine already has bounded pool configuration,
   pre-ping, recycling, session lifecycle management, and explicit transaction
   handling.

5. **Migration cost would be substantial**

   A full async migration would affect:

   - route handlers;
   - database dependencies;
   - services;
   - authentication flows;
   - refresh-token locking;
   - MFA;
   - OIDC;
   - session management;
   - transactional outbox behavior;
   - worker code;
   - tests;
   - tracing;
   - debugging and operational procedures.

6. **Complexity is not justified by measured benefit**

   Architectural complexity should not be increased merely because async APIs
   are available.

## What this decision does not mean

This evaluation does not conclude that async SQLAlchemy is universally slower
than synchronous SQLAlchemy.

The result applies to:

- this application;
- these database workloads;
- this pool configuration;
- this PostgreSQL environment;
- this benchmark host;
- this driver;
- the measured concurrency range.

Async may be beneficial for applications with different workload profiles,
especially when request execution spends substantial time waiting on multiple
independent network operations.

## Conditions for reconsidering async

Repeat the evaluation before considering migration if one or more of the
following become true:

- production concurrency substantially exceeds the tested range;
- database waits dominate request execution;
- application workers are demonstrably blocked by synchronous database I/O;
- the service begins coordinating several independent async I/O operations per
  request;
- production telemetry shows worker starvation despite adequate PostgreSQL
  capacity;
- deployment architecture changes materially;
- database or driver behavior changes;
- a new async implementation shows a reproducible improvement under
  production-like conditions.

A future decision should again compare equivalent transaction semantics,
connection limits, datasets, and query shapes.

## Optimization priorities before async migration

Based on the current measurements, future database performance work should
prioritize:

1. query-plan and index analysis;
2. connection-pool sizing;
3. reducing unnecessary row materialization;
4. minimizing transaction duration;
5. reviewing high-contention update paths;
6. optimizing session-list processing if production telemetry identifies it
   as significant;
7. PostgreSQL configuration and capacity;
8. realistic end-to-end HTTP load testing.

These optimizations address the measured bottlenecks more directly than a
wholesale async migration.

## Running the synchronous benchmark

Example:

```bash
python scripts/benchmarks/db_benchmark.py \
  --scenario user-read \
  --concurrency 4 \
  --duration 10 \
  --warmup 2 \
  --fixture-sessions 50 \
  --output benchmark-results/sync-user-read-c4.json
```

Supported scenarios:

```text
user-read
session-list
refresh-lock
session-revoke
mixed
```

## Running the async benchmark

Example:

```bash
python scripts/benchmarks/async_db_benchmark.py \
  --scenario user-read \
  --concurrency 4 \
  --duration 10 \
  --warmup 2 \
  --fixture-sessions 50 \
  --output benchmark-results/async-user-read-c4.json
```

The async benchmark uses Psycopg 3 through:

```text
postgresql+psycopg
```

No `asyncpg` dependency is required for this evaluation.

## Benchmark result files

Raw benchmark JSON is written under:

```text
benchmark-results/
```

This directory is intentionally ignored by Git.

Raw results are machine-specific and are not treated as stable repository
artifacts.

The measured findings and architectural conclusion are recorded in this
document instead.

## Reproducibility guidance

For meaningful comparisons:

- run sync and async measurements on the same host;
- use the same PostgreSQL instance;
- keep pool settings identical;
- keep the dataset and fixture count identical;
- keep warm-up and duration identical;
- avoid other heavy workloads while measuring;
- repeat measurements before treating small differences as significant;
- do not compare results collected on substantially different hardware;
- do not infer regressions from shared CI runner timing alone.

For higher-confidence production decisions, repeat benchmarks multiple times
and report distribution statistics across runs instead of relying on a single
measurement.

## Limitations

This evaluation has several deliberate limitations:

- measurements were produced on a local workstation;
- results are not production SLOs;
- CPU and memory utilization were not yet recorded automatically by the
  benchmark harness;
- PostgreSQL server-side wait events were not collected;
- query-plan analysis was outside this issue;
- HTTP routing and middleware overhead were not included in the core database
  benchmark;
- Redis performance was intentionally excluded;
- OIDC external-provider latency was intentionally excluded;
- MFA cryptographic work was intentionally excluded;
- the benchmark does not model multiple application processes;
- the benchmark does not model geographically remote PostgreSQL;
- the async prototype uses Psycopg async rather than `asyncpg`.

These limitations do not invalidate the sync-vs-async result for the tested
database workloads, but they constrain how broadly the numbers should be
generalized.

## Follow-up

No full async SQLAlchemy migration issue is required based on the current
results.

Future performance work should focus on measured application and PostgreSQL
bottlenecks rather than changing the database programming model without
evidence.

The async decision should be revisited only when production telemetry or a
material architecture change provides a reason to repeat this evaluation.
