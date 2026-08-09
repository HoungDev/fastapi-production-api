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

This repository includes a complete single-host example below. It does not yet
ship a production image or orchestration manifest. On a container platform, use
the same locked install and migration rules, start the application with
`uv run uvicorn app.main:app --host 0.0.0.0 --port 8000`, configure liveness and
readiness separately, and expose `/metrics` only to the monitoring network.

## 1. Prepare the server

Recommended baseline:

- Ubuntu 24.04 LTS or an equivalent supported Linux distribution
- Python 3.13+
- PostgreSQL 17+
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
EMAIL_DELIVERY_MODE=smtp
EMAIL_VERIFICATION_URL=https://your-frontend.example/verify-email
PASSWORD_RESET_URL=https://your-frontend.example/reset-password
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

## Release sequence

A safe deployment separates schema changes from worker startup:

1. Back up the database and verify restoration procedures.
2. Install the reviewed release tag or immutable commit.
3. Apply migrations once as a dedicated release step.
4. Start or roll application workers.
5. Wait for `/health/ready` before sending traffic.
6. Smoke-test authentication and operational endpoints.
7. Monitor errors, readiness, latency, and database health during rollout.

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
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
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

Only trust forwarded headers from proxies you control. Configure firewall rules
so the Gunicorn port is not publicly reachable.

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

The built-in rate limiter is process-local. For multiple workers or hosts,
enforce distributed limits through Redis, an API gateway, or the edge proxy.
See [MONITORING.md](MONITORING.md) for Prometheus scraping, multi-worker metric
aggregation, correlation IDs, alert ideas, and troubleshooting.
See [ARCHITECTURE.md](ARCHITECTURE.md) for application trust boundaries and
[API_EXAMPLES.md](API_EXAMPLES.md) for authenticated smoke-test requests.

## Release checklist

- [ ] Deploy a reviewed release tag or commit SHA
- [ ] Store secrets outside version control
- [ ] Back up the production database
- [ ] Test migrations and rollback procedures in staging
- [ ] Run test, lint, and dependency-audit jobs successfully
- [ ] Restrict database and service-account permissions
- [ ] Restrict the application port to the trusted proxy
- [ ] Enable HTTPS and renewal monitoring
- [ ] Configure logs, metrics, alerts, and retention
- [ ] Configure database backups and test restoration
- [ ] Verify `/health/live`, `/health/ready`, and `/metrics` after deployment
