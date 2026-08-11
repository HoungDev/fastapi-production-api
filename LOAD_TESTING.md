# Load testing

The repository includes a bounded [Grafana k6](https://grafana.com/docs/k6/latest/)
example for end-to-end HTTP behavior. It complements the database-only harness
in [DATABASE_BENCHMARKS.md](DATABASE_BENCHMARKS.md): k6 measures routing, JWT,
password hashing, database access, middleware, and response serialization as one
system.

## Safety and scope

Run the example only against an isolated local or explicitly authorized staging
environment. It creates disposable users and refresh-token sessions and does not
delete them. Use a disposable database or restore a snapshot after the run.

Remote targets are rejected unless `ALLOW_REMOTE_TARGET=true`. That override is
an acknowledgement, not a safety guarantee. Never point this script at
production, and confirm the expected traffic with the environment owner before
raising concurrency.

The default thresholds are reviewable starting points, not universal SLOs:

- fewer than 1% failed workload requests;
- more than 99% successful checks;
- workload p95 below 500 ms and p99 below 1,000 ms.

Change thresholds only from measured service objectives. Retain the k6 summary,
application metrics, PostgreSQL/Redis metrics, CPU, memory, commit SHA, and
environment configuration with every result.

## Profiles

| Profile | Behavior | Intended use |
| --- | --- | --- |
| `health` | Repeated `GET /health/live` after a readiness probe | Network and middleware baseline |
| `authenticated` | One user/session per VU, repeated `GET /auth/me`, periodic refresh rotation | Representative authentication lifecycle |

Registration and login happen outside the tagged workload latency thresholds.
They are still checked and visible in the k6 result. Each virtual user owns its
refresh token so rotations do not create artificial replay failures.

## Local smoke run

Start PostgreSQL and Redis, apply migrations, and start the API as described in
[DEVELOPMENT.md](DEVELOPMENT.md). Install k6 1.x, then run:

```bash
k6 run -e PROFILE=health -e VUS=2 -e DURATION=10s load_tests/api.js
k6 run -e PROFILE=authenticated -e VUS=5 -e DURATION=30s load_tests/api.js
```

PowerShell uses the same commands. The defaults target
`http://127.0.0.1:8000`, use five virtual users for 30 seconds, and rotate each
virtual user's refresh token every 20 iterations.

Useful environment variables:

| Variable | Default | Meaning |
| --- | --- | --- |
| `BASE_URL` | `http://127.0.0.1:8000` | API origin without a trailing slash |
| `PROFILE` | `authenticated` | `health` or `authenticated` |
| `VUS` | `5` | Concurrent virtual users |
| `DURATION` | `30s` | k6 duration expression |
| `REFRESH_EVERY` | `20` | Authenticated iterations between rotations |
| `RUN_ID` | current timestamp | Suffix making generated usernames unique |
| `LOAD_TEST_PASSWORD` | disposable local value | Password for generated users |
| `ALLOW_REMOTE_TARGET` | unset | Must be exactly `true` for a remote host |

Validate the script without sending traffic:

```bash
k6 inspect load_tests/api.js
```

## Staged workload

Establish a baseline before looking for capacity limits:

1. Run `health` with one VU to record network/middleware latency.
2. Run `authenticated` at 1, 5, 10, and 25 VUs for at least five minutes each.
3. Repeat every point three times on the same commit and unchanged environment.
4. Stop when error rate, pool wait, CPU saturation, or tail latency violates the
   service objective; do not keep increasing traffic through an unhealthy API.
5. Diagnose bcrypt cost, database pool pressure, Redis latency, worker count,
   and tracing export separately before changing the application architecture.

CI shared runners should only validate correctness and script structure. Do not
use their timings as a release performance gate. A release gate belongs in a
controlled staging environment with stable infrastructure and retained results.

