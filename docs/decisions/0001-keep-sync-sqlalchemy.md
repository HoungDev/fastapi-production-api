# ADR 0001: Keep synchronous SQLAlchemy for v1.3.0

- Status: accepted
- Date: 2026-08-11
- Decision owners: maintainers

## Context

The application uses synchronous SQLAlchemy and psycopg with explicit request
sessions and transaction rollback. Async SQLAlchemy may improve concurrency for
some database-wait-heavy workloads, but a full conversion would affect routers,
services, repositories, tests, tracing, workers, and operational debugging.

## Decision

Keep the production path synchronous for v1.3.0. Maintain the asyncpg prototype
only in the opt-in benchmark harness. Do not expose an async session dependency
to application code and do not change API, authentication, outbox, or migration
semantics.

## Rationale

The repository has no representative extended measurement demonstrating that a
migration would produce a meaningful SLO improvement. CI smoke timing is noisy
and is used only for correctness. The simplest architecture satisfying current
evidence is therefore the existing synchronous path.

## Consequences

- Production behavior and operational knowledge remain stable.
- Sync and async can be compared with equivalent SQL, fixtures, pools, and
  transaction boundaries using `DATABASE_BENCHMARKS.md`.
- Teams must run and retain representative extended results before reopening
  the decision.
- A full async migration, if justified later, requires a separate scoped issue.

