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
```

Prefer a managed secrets service over a file when your platform supports one.
The database user should have only the permissions required by the application.

## 4. Apply migrations

Back up the database and test migrations in staging before production:

```bash
uv run alembic upgrade head
```

Run migrations once per release, not concurrently in every worker.

## 5. Smoke-test the service

```bash
uv run gunicorn -c gunicorn.conf.py app.main:app
```

From another terminal:

```bash
curl --fail http://127.0.0.1:8000/health
curl --fail http://127.0.0.1:8000/health/db
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
- [ ] Verify `/health` and `/health/db` after deployment
