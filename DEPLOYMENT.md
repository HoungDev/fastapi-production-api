# Production Deployment Guide

This guide describes a conventional self-hosted Linux deployment using
PostgreSQL, Gunicorn with the standalone Uvicorn worker, systemd, Nginx, and
TLS. Adapt it to your infrastructure and threat model.

## Reference architecture

```text
Internet
   |
Nginx (TLS and trusted proxy headers)
   |
Gunicorn + uvicorn-worker
   |
FastAPI
   |
PostgreSQL
```

For container orchestration, prefer one Uvicorn process per container and scale
at the container level.

## Choose a deployment pattern

| Pattern | Process model | Best fit |
| --- | --- | --- |
| Single Linux host | Nginx -> Gunicorn -> Uvicorn workers | Small services with direct host operations |
| Container platform | Load balancer -> one Uvicorn process per container | Platforms that own restarts, health probes, and horizontal scaling |

This repository includes both the complete single-host example below and a
multi-stage production `Dockerfile`. The image runs one Uvicorn process as an
unprivileged user, contains only locked runtime dependencies, and provides a
liveness healthcheck. Container platforms must still configure readiness,
release migrations, secrets, ingress, and restricted metrics exposure.

## Production container image

Build an immutable image from a reviewed tag or commit:

```bash
docker build --pull --tag fastapi-production-api:<version> .
```

The runtime image does not contain the source checkout, `uv`, test tools, or an
environment file. Inject configuration at runtime and run migrations as a
separate release task before starting application replicas:

```bash
docker run --rm --env-file .env \
  fastapi-production-api:<version> alembic upgrade head

docker run --detach --name fastapi-production-api \
  --env-file .env \
  --publish 8000:8000 \
  --read-only --tmpfs /tmp \
  --cap-drop ALL --security-opt no-new-privileges:true \
  fastapi-production-api:<version>
```

Ensure database, Redis, SMTP, OIDC, and telemetry hostnames in `.env` resolve
from the container network. Do not run migrations in every replica's startup
command. Use `/health/live` for container restart decisions and `/health/ready`
for traffic admission. The image healthcheck intentionally uses liveness so a
temporary database outage does not create a restart loop.

## 1. Prepare the server

Recommended baseline:

- Ubuntu 24.04 LTS or an equivalent supported Linux distribution
- Python 3.13+
- PostgreSQL 17+
- Redis 8+
- Nginx
- Git
- [uv](https://docs.astral.sh/uv/)

Create a dedicated, unprivileged service account. Do not run the API as root.

## 2. Install the application

```bash
git clone https://github.com/HoungDev/fastapi-production-api.git
cd fastapi-production-api
git checkout <release-tag>
uv sync --locked --no-dev
```

Deploy an immutable release tag or commit SHA, not a moving development branch.

## 3. Configure secrets and environment

```bash
cp .env.production.example .env
chmod 600 .env
```

Generate a secret instead of reusing the example value:

```bash
uv run python -c "import secrets; print(secrets.token_urlsafe(48))"
```

At minimum, review:

```env
ENVIRONMENT=production
DEBUG=false
DATABASE_URL=postgresql+psycopg://user:strong-password@database-host/app
SECRET_KEY=<generated-secret>
JWT_AUDIENCE=fastapi-client
JWT_ISSUER=fastapi-production-api
CORS_ORIGINS=https://your-frontend.example
REDIS_URL=rediss://app:<password>@redis.internal.example:6379/0
RATE_LIMIT_BACKEND=redis
RATE_LIMIT_KEY_SECRET=<generated-dedicated-secret>
RATE_LIMIT_FAILURE_MODE=closed
EMAIL_DELIVERY_MODE=outbox
OUTBOX_ENCRYPTION_KEY=<dedicated-fernet-key>
OUTBOX_BATCH_SIZE=10
OUTBOX_LEASE_SECONDS=30
OUTBOX_MAX_ATTEMPTS=5
OUTBOX_BACKOFF_BASE_SECONDS=5
OUTBOX_BACKOFF_MAX_SECONDS=300
OUTBOX_SHUTDOWN_GRACE_SECONDS=30
EMAIL_VERIFICATION_URL=https://your-frontend.example/verify-email
PASSWORD_RESET_URL=https://your-frontend.example/reset-password
MFA_ENABLED=true
MFA_ENCRYPTION_KEY=<dedicated-fernet-key>
OIDC_ENABLED=false
OIDC_ISSUER=https://identity-provider.example
OIDC_CLIENT_ID=<provider-client-id>
OIDC_CLIENT_SECRET=<provider-client-secret>
OIDC_REDIRECT_URI=https://api.your-domain.example/auth/oidc/callback
OIDC_TRANSACTION_ENCRYPTION_KEY=<dedicated-fernet-key>
TRACING_ENABLED=false
OTEL_SERVICE_NAME=fastapi-production-api
OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector.internal.example:4318
OTEL_EXPORT_TIMEOUT_SECONDS=5
OTEL_TRACE_SAMPLE_RATIO=0.1
SMTP_HOST=smtp.example.com
SMTP_FROM=security@your-domain.example
```

Prefer a managed secrets service over a file when your platform supports one.
The database user should have only the permissions required by the application.
Keep `SMTP_PASSWORD` in the same secrets system as `SECRET_KEY`. Use an exact
HTTPS verification URL controlled by your application, and never place raw
verification tokens in logs, metrics, analytics, or support tickets.
Password reset revokes all refresh tokens, but it cannot immediately invalidate
already-issued stateless access tokens. Keep access-token lifetimes short and
use a server-side token version or denylist if your threat model requires
immediate revocation.

Generate `RATE_LIMIT_KEY_SECRET` independently from JWT and encryption keys.
Redis quota keys contain only a versioned HMAC identifier and fixed-window
number; rotating this key safely resets active quota buckets. Keep fail-closed
unless an explicit availability decision accepts temporary unprotected traffic.

Generate the MFA encryption key independently from the JWT signing key:

```bash
uv run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Store `MFA_ENCRYPTION_KEY` in the deployment secrets manager and back it up.
Losing it makes enrolled authenticator seeds unreadable; disclosure requires
rotating the key and re-enrolling affected users. Never log this key, decrypted
TOTP seeds, login challenges, or recovery codes. TOTP is replay-resistant in
this implementation but remains susceptible to real-time phishing; use
WebAuthn/passkeys where phishing resistance is required.

Register `OIDC_REDIRECT_URI` exactly with the provider and enable OIDC only after
verifying discovery metadata, supported signing algorithms, and PKCE S256. Use
a second Fernet key for `OIDC_TRANSACTION_ENCRYPTION_KEY`; do not reuse the JWT
or MFA key. The callback does not accept caller-selected redirect targets.
Provider client secrets, codes, ID/access tokens, PKCE verifiers, state, nonce,
and browser-binding values must not enter logs or analytics. OAuth access tokens
alone are not user identity proof; this flow requires a validated OIDC ID token.

## 4. Apply migrations

Back up the database and test migrations in staging before production:

```bash
uv run alembic upgrade head
```

Run migrations once per release, not concurrently in every worker.

When upgrading from v1.1.0, the email-verification migration normalizes existing
non-null email addresses before adding the lifecycle table. Audit existing
addresses for case-insensitive duplicates in staging first; the migration must
stop rather than silently merge conflicting identities. Test both `upgrade
head` and downgrade to revision `906770b858da` against a backup or disposable
copy before production rollout.

The session-management migration assigns every pre-existing refresh token its
own legacy family, then makes family and device metadata required. This avoids
accidentally joining unrelated historical tokens. Apply and roll back the
migration on a staging copy with representative token volume; rotation now uses
row locks and replay revocation, so the production database must support the
same transaction behavior as PostgreSQL.

The MFA migration adds nullable user enrollment fields and a separate recovery
code table, so existing password-only accounts remain compatible. Apply it
before enabling `MFA_ENABLED`; test downgrade only on a disposable copy because
it removes enrollment state and recovery-code hashes.

The OIDC migration marks existing users as password-login enabled, then adds
external identities and short-lived authorization transactions. OIDC-created
users are explicitly marked as password-login disabled until they complete the
verified password-reset lifecycle. Test downgrade on a disposable database;
it removes identity links and pending authorization transactions.

## Release sequence

A safe deployment separates schema changes from worker startup:

1. Back up the database and verify restoration procedures.
2. Install the reviewed release tag or immutable commit.
3. Apply migrations once as a dedicated release step.
4. Start or roll API processes.
5. Start one or more `fastapi-production-worker` processes after the outbox
   migration is present.
6. Wait for `/health/ready` before sending traffic.
7. Smoke-test authentication and operational endpoints.
8. Monitor errors, readiness, latency, outbox backlog, and dead letters.

Prefer backward-compatible expand-and-contract migrations when old and new
workers may overlap. Application rollback does not automatically reverse a
database migration; document and rehearse the data-safe rollback separately.

## 5. Smoke-test the service

```bash
uv run gunicorn -c gunicorn.conf.py app.main:app
```

From another terminal:

```bash
curl --fail http://127.0.0.1:8000/health
curl --fail http://127.0.0.1:8000/health/live
curl --fail http://127.0.0.1:8000/health/ready
curl --fail http://127.0.0.1:8000/metrics
```

## 6. Configure systemd

Create `/etc/systemd/system/fastapi-production-api.service`:

```ini
[Unit]
Description=FastAPI Production API
After=network-online.target postgresql.service
Wants=network-online.target

[Service]
Type=notify
User=fastapi
Group=fastapi
WorkingDirectory=/opt/fastapi-production-api
EnvironmentFile=/opt/fastapi-production-api/.env
Environment=PROMETHEUS_MULTIPROC_DIR=/run/fastapi-production-api/metrics
RuntimeDirectory=fastapi-production-api
ExecStartPre=/usr/bin/install -d -m 0750 /run/fastapi-production-api/metrics
ExecStartPre=/usr/bin/find /run/fastapi-production-api/metrics -type f -delete
ExecStart=/home/fastapi/.local/bin/uv run gunicorn -c gunicorn.conf.py app.main:app
Restart=on-failure
RestartSec=5
TimeoutStopSec=30
PrivateTmp=true
NoNewPrivileges=true

[Install]
WantedBy=multi-user.target
```

Adjust paths and the service account for your server, then enable the unit:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now fastapi-production-api
sudo systemctl status fastapi-production-api
```

## 7. Configure Nginx

```nginx
server {
    listen 80;
    server_name api.example.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location = /metrics {
        allow 10.0.0.0/8;
        deny all;
        proxy_pass http://127.0.0.1:8000/metrics;
    }
}
```

Validate and reload:

```bash
sudo nginx -t
sudo systemctl reload nginx
```

`FORWARDED_ALLOW_IPS` is the trust boundary for both client IP and forwarded
scheme resolution. Set it to the socket peers that connect directly to
Gunicorn, for example `127.0.0.1` for same-host Nginx or a comma-separated list
of canonical proxy CIDRs. The default is empty, and the application rejects
wildcard, malformed, and non-canonical entries. Never list client networks.

The single-proxy example overwrites `X-Forwarded-For` with `$remote_addr`, so a
client-supplied value cannot enter the trusted chain. For a controlled
multi-proxy topology, each trusted proxy may append its verified peer address;
list every direct intermediary CIDR and test the chain before deployment.

Uvicorn validates the socket peer before updating the ASGI client address. Rate
limiting and request logs consume only that canonical ASGI address and do not
parse forwarding headers again. Keep the Gunicorn port firewalled from
untrusted clients even when the allowlist is configured.

## 8. Enable HTTPS

Use your platform certificate manager or Certbot:

```bash
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d api.example.com
```

Redirect HTTP to HTTPS and verify certificate renewal.

## 9. Operate the service

```bash
journalctl -u fastapi-production-api -f
sudo systemctl restart fastapi-production-api
```

Set `RATE_LIMIT_BACKEND=redis` for shared limits across workers or hosts. Redis
outages are fail-closed by default; an explicitly configured fail-open policy is
observable in logs and metrics. Roll back without data migration by selecting
`RATE_LIMIT_BACKEND=memory`, accepting process-local quotas until Redis returns.

Run durable email delivery as a separate systemd service using the same release,
database URL, SMTP settings, and `OUTBOX_ENCRYPTION_KEY` as the API:

```ini
[Service]
WorkingDirectory=/opt/fastapi-production-api
EnvironmentFile=/opt/fastapi-production-api/.env
ExecStart=/opt/fastapi-production-api/.venv/bin/fastapi-production-worker
Restart=on-failure
TimeoutStopSec=40
```

Scale by starting identical worker instances. `SIGTERM` stops new claims and
allows bounded graceful completion. Delivery is at-least-once; do not advertise
exactly-once SMTP semantics. During rollback, stop outbox-mode API writers and
workers before deploying synchronous mode. Pending encrypted rows may remain
for a forward recovery, but old code must not drop the outbox table. Drain
pending jobs before rotating the encryption key; key loss makes them
undecryptable, while key disclosure requires replacement and fresh lifecycle
tokens.
See [MONITORING.md](MONITORING.md) for Prometheus scraping, multi-worker metric
aggregation, correlation IDs, alert ideas, and troubleshooting.
See [ARCHITECTURE.md](ARCHITECTURE.md) for application trust boundaries and
[API_EXAMPLES.md](API_EXAMPLES.md) for authenticated smoke-test requests.

## OpenTelemetry tracing rollout and rollback

Tracing is optional and should be rolled out independently from application
correctness. Keep `TRACING_ENABLED=false` for the first deployment of a new
application version, verify normal API and worker behavior, then enable tracing
after the OTLP Collector endpoint is reachable.

Recommended production configuration:

    TRACING_ENABLED=true
    OTEL_SERVICE_NAME=fastapi-production-api
    OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector.internal.example:4318
    OTEL_EXPORT_TIMEOUT_SECONDS=5
    OTEL_TRACE_SAMPLE_RATIO=0.1

Collector failure is intentionally not part of `/health/ready`. Exporter
timeouts are bounded, and tracing must degrade without failing normal API
requests, database operations, Redis operations, OIDC calls, or outbox worker
jobs.

Do not embed credentials in `OTEL_EXPORTER_OTLP_ENDPOINT`. Restrict access to
the Collector and trace backend, configure retention deliberately, and review
sampling against traffic volume and privacy requirements.

Migration `65bcb8a12535` adds nullable bounded `traceparent` and `tracestate`
columns to the transactional outbox. Existing rows remain compatible.

To disable tracing without rolling back the schema:

    TRACING_ENABLED=false

Restart API and worker processes after changing this setting.

If the tracing schema itself must be rolled back, stop new API writers and
outbox workers first, then downgrade to `f3a6c8d91b42`. This removes only the
trace-context columns; tracing metadata is not a correctness dependency.

## Release checklist

- [ ] Deploy a reviewed release tag or commit SHA
- [ ] Store secrets outside version control
- [ ] Back up the production database
- [ ] Test migrations and rollback procedures in staging
- [ ] Run test, lint, and dependency-audit jobs successfully
- [ ] Build the production image and smoke-test liveness/readiness as non-root
- [ ] Restrict database and service-account permissions
- [ ] Restrict the application port to the trusted proxy
- [ ] Set `FORWARDED_ALLOW_IPS` to direct proxy peers only and test spoofed headers
- [ ] Enable HTTPS and renewal monitoring
- [ ] Configure logs, metrics, alerts, and retention
- [ ] Configure database backups and test restoration
- [ ] Verify `/health/live`, `/health/ready`, and `/metrics` after deployment
- [ ] Verify workers claim jobs, recover expired leases, and shut down cleanly
- [ ] Alert on old pending jobs, retry growth, and dead-letter growth

## OIDC cache operation, rotation, and rollback

OIDC discovery and JWKS caching is an optional Redis-backed optimization.
Deployments should initially leave `OIDC_CACHE_BACKEND=none`, verify the new
application version, and only then enable `OIDC_CACHE_BACKEND=redis` after the
Redis endpoint is reachable from every API instance.

The Redis cache is shared by application processes so discovery and JWKS
fetches do not need to be repeated independently by every worker. Entries have
bounded TTLs and refresh coordination uses expiring locks. The implementation
does not require Redis Cluster, Sentinel, or another distributed Redis
topology.

Only public provider documents are cached. Authentication decisions, bearer
tokens, ID tokens, token claims, sessions, user records, and other private
authentication state are never written to this cache.

### Provider and Redis failure behavior

A Redis read, write, or lock failure does not make Redis authoritative. The API
falls back to fetching the document from the configured OIDC provider. Cached
documents are validated after every read and malformed or oversized values are
discarded.

Expired cache entries are not trusted as a stale authentication fallback. If
the provider is also unavailable, OIDC processing returns its controlled
provider failure instead of accepting an expired document.

Provider HTTP requests retain the normal OIDC transport protections, including
redirect refusal and bounded response sizes.

### Signing-key rotation

Publish a new signing key in the provider JWKS before beginning to issue tokens
with that key. If an otherwise valid cached JWKS does not contain a token's
`kid`, the application performs one direct JWKS refresh and then repeats the
normal key and algorithm checks.

For an operator-controlled refresh, invalidate only the configured issuer:

```bash
fastapi-production-cache invalidate-oidc
```

When running from the source checkout, the equivalent command is:

```bash
uv run fastapi-production-cache invalidate-oidc
```

Manual invalidation removes only this application's discovery and JWKS entries
for the configured issuer; it must not use `FLUSHDB`, `FLUSHALL`, wildcard
deletion, or a Redis-wide key scan.

### Rollout

A safe production rollout is:

1. deploy the release with `OIDC_CACHE_BACKEND=none`;
2. confirm existing OIDC login and token validation remain healthy;
3. verify Redis connectivity from all API instances;
4. enable `OIDC_CACHE_BACKEND=redis` and restart the API instances;
5. watch OIDC cache/provider metrics and structured logs for cache errors,
   provider errors, refreshes, and lock contention;
6. verify normal authentication and a planned cache invalidation.

### Rollback

Caching can be disabled without a database migration or Redis data migration.
Set:

```env
OIDC_CACHE_BACKEND=none
```

and restart the API processes. The application then resumes direct discovery
and JWKS retrieval from the provider. Existing Redis entries may be allowed to
expire naturally or may be removed with the scoped `invalidate-oidc` command.

Do not change the package version solely for this feature branch. Version
changes remain part of the final v1.3.0 release preparation.
