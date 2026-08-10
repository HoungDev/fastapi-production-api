# Monitoring and Troubleshooting

The API exposes health probes, Prometheus metrics, and structured JSON logs.
Keep operational endpoints reachable from your monitoring network, but do not
publish `/metrics` directly to the internet.

## Health probes

| Endpoint | Meaning | Dependency check | Failure action |
| --- | --- | --- | --- |
| `/health/live` | The application process can serve HTTP | None | Restart the process |
| `/health/ready` | The application can serve traffic | PostgreSQL and Redis when distributed limiting is enabled | Remove the instance from service |

Readiness returns HTTP `503` while PostgreSQL is unavailable. Liveness must not
depend on PostgreSQL; otherwise a database incident can cause every application
instance to restart at once. `/health` and `/health/db` remain as deprecated
compatibility aliases.

With `RATE_LIMIT_BACKEND=redis`, readiness includes separate `database` and
`redis` checks and returns `503` if either is unavailable. Redis never affects
liveness, which prevents dependency incidents from causing restart loops.

Example Kubernetes probes:

```yaml
livenessProbe:
  httpGet:
    path: /health/live
    port: 8000
readinessProbe:
  httpGet:
    path: /health/ready
    port: 8000
```

## Prometheus metrics

Configure Prometheus to scrape `/metrics`:

```yaml
scrape_configs:
  - job_name: fastapi-production-api
    metrics_path: /metrics
    static_configs:
      - targets: ["api.internal.example:8000"]
```

The application exports:

- `fastapi_production_api_http_requests_total`, labelled by method, route
  template, and status code
- `fastapi_production_api_http_request_duration_seconds`, a latency histogram
  labelled by method and route template
- `fastapi_production_api_http_requests_in_progress`, labelled by method
- `fastapi_production_api_rate_limit_decisions_total`, labelled by backend and
  the bounded outcomes `allowed`, `blocked`, `fail_open`, or `fail_closed`
- `fastapi_production_api_rate_limit_backend_errors_total`, labelled by backend
  and bounded operation category
- `fastapi_production_api_outbox_messages_total`, labelled by bounded message
  type and outcome
- `fastapi_production_api_outbox_failures_total`, labelled by bounded failure
  category
- `fastapi_production_api_outbox_delivery_duration_seconds`, labelled by
  bounded message type

Route templates are used instead of raw URLs to bound label cardinality. Protect
the endpoint with network policy, firewall rules, or an allowlist at the reverse
proxy. Health and metrics endpoints bypass the application request limiter so
monitoring remains reliable during traffic spikes; the network boundary must
therefore enforce access policy and abuse protection for them.

### Multiple Gunicorn workers

Prometheus metrics must be aggregated across worker processes. Create and empty
a worker-writable directory before each Gunicorn start, then export it before
Python imports the application:

```bash
install -d -m 0750 /run/fastapi-production-api/metrics
find /run/fastapi-production-api/metrics -type f -delete
export PROMETHEUS_MULTIPROC_DIR=/run/fastapi-production-api/metrics
uv run gunicorn -c gunicorn.conf.py app.main:app
```

Do not reuse files from a previous Gunicorn run. The included Gunicorn
configuration marks worker gauge files as dead when workers exit.

## Structured logs and correlation IDs

Every application log is a single JSON object containing `timestamp`, `level`,
`logger`, `message`, and `request_id`. HTTP completion records also contain
`method`, `path`, `route`, `status_code`, and `duration_ms`.

When a valid OpenTelemetry span is active, the same JSON record also contains
hexadecimal `trace_id` and `span_id` values. This allows operators to correlate
logs and distributed traces without replacing the existing `request_id`
workflow.

Clients may send `X-Request-ID` using 1-128 letters, digits, dots, underscores,
colons, or hyphens. Invalid or missing values are replaced with a generated ID,
and the effective value is returned in the response header. Forward this header
through proxies and include it in downstream service logs.

## OpenTelemetry tracing

Tracing is disabled by default. Enable it only after an OTLP/HTTP-compatible
Collector is available.

    TRACING_ENABLED=true
    OTEL_SERVICE_NAME=fastapi-production-api
    OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector.internal.example:4318
    OTEL_EXPORT_TIMEOUT_SECONDS=5
    OTEL_TRACE_SAMPLE_RATIO=0.1

The application instruments FastAPI inbound requests, SQLAlchemy operations,
HTTPX outbound calls, Redis operations, and transactional outbox worker
execution. W3C Trace Context is propagated through the outbox using only
bounded `traceparent` and `tracestate` values.

Trace attributes intentionally exclude request and response bodies,
authorization headers, cookies, raw query strings, credentials, email
addresses, lifecycle tokens, OIDC state, nonce, PKCE values, and authorization
codes.

Collector failure must not make `/health/ready` fail. If traces stop arriving
while readiness, Prometheus metrics, and application logs remain healthy,
inspect Collector reachability, OTLP endpoint configuration, sampling, backend
ingestion, and retention before restarting application processes.

To correlate one request, capture its `X-Request-ID`, find the JSON
`http_request` log, read `trace_id` and `span_id` when present, then query the
trace backend by `trace_id`.

## Baseline alert ideas

- Readiness failing for more than two scrape intervals
- Five-minute 5xx ratio above the service error-budget threshold
- P95 request latency above the endpoint service-level objective
- No healthy targets or no recent metric samples
- Repeated `database_readiness_check_failed` log events
- Redis readiness failures or sustained fail-open/fail-closed decisions
- Old pending outbox work, growing retries/dead letters, expired leases, or no
  active worker process

Tune thresholds from measured traffic; the repository cannot choose meaningful
service-level objectives for a specific deployment.

## Troubleshooting

### The process is live but not ready

1. Call `/health/ready` and confirm it returns `503`.
2. Search logs for `database_readiness_check_failed` using the response's
   `X-Request-ID` where applicable.
3. Verify database DNS, network policy, credentials, connection limits, and the
   current migration state.
4. Restore dependency access before routing traffic back to the instance. Do
   not change liveness to restart-loop the service during a database outage.

### Metrics are missing across multiple workers

1. Confirm `PROMETHEUS_MULTIPROC_DIR` was exported before Gunicorn started.
2. Confirm the directory exists and is writable by the service account.
3. Empty the directory before a full Gunicorn restart.
4. Confirm Prometheus can reach `/metrics` and is not blocked by the proxy
   allowlist.

### Redis is unavailable

1. Check the `redis` readiness result and the configured outage policy.
2. Inspect Redis DNS, TLS, credentials, connection limits, and latency without
   logging the Redis URL or password.
3. Fail-closed returns `503`; explicit fail-open continues traffic and emits a
   decision metric and structured warning.
4. Restore Redis access. Quota enforcement resumes without restarting the API.

### Outbox backlog is growing

1. Inspect counts and oldest `available_at` by state without selecting
   `payload_encrypted`.
2. Confirm workers are running with the same database and encryption-key
   configuration as the API.
3. Check bounded `smtp`, `invalid_payload`, `expired`, and `worker_loop`
   categories; logs intentionally omit provider exception text.
4. Restore PostgreSQL/SMTP access. Pending and expired-lease work resumes
   without restarting every worker.
5. Dead-letter rows have already purged sensitive payloads. Ask the user to
   request a fresh lifecycle token rather than replaying the row.

### Follow one failed request

Capture `X-Request-ID` from the response and search the JSON logs for the same
`request_id`. Start with the `http_request` record, then inspect application and
database events carrying that correlation ID. Avoid logging authorization
headers, tokens, passwords, or request bodies while debugging.

## OIDC cache observability

Redis-backed OIDC caching exports bounded, low-cardinality observations for
cache reads, refreshes, invalid documents, invalidation, refresh-lock behavior,
provider fetches, and failures. Provider fetch duration is also observable.

To inspect the relevant Prometheus series during troubleshooting:

```bash
curl -fsS http://127.0.0.1:8000/metrics | grep -E 'oidc_(cache|provider)'
```

Useful operational signals include sustained increases in cache errors,
provider-fetch failures, forced JWKS refreshes, invalid cached documents, or
refresh-lock contention. A cache miss by itself is normal, especially after
startup, TTL expiry, or manual invalidation.

OIDC cache logs intentionally use bounded event/document fields. They must not
include bearer tokens, ID tokens, claims, signing keys, Redis credentials,
complete Redis URLs, raw issuer-derived cache keys, or other secrets.

### OIDC cache Redis outage

If Redis becomes unavailable, OIDC discovery and JWKS loading should fall
through to the provider. Check application logs and OIDC cache metrics for the
Redis error, then confirm that the provider remains reachable.

If Redis instability is persistent, disable only this optimization:

```env
OIDC_CACHE_BACKEND=none
```

Restart the API instances after changing the setting. OIDC then continues with
direct provider requests.

Do not treat an expired Redis document as a stale authentication fallback.

### OIDC signing-key rotation

A token containing an unknown `kid` while the JWKS came from cache causes one
provider JWKS refresh. If the key remains absent after that refresh, token
validation is rejected normally.

For planned provider changes or when operators need an immediate refresh, run:

```bash
fastapi-production-cache invalidate-oidc
```

Then verify that the next request repopulates the discovery/JWKS cache from the
provider.

If validation still fails after invalidation, check the provider's published
JWKS, issuer configuration, signing algorithm, audience, and key-rotation
sequence before changing cache behavior.
