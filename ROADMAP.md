# Roadmap

FastAPI Production API aims to be a practical, security-focused foundation for
building and learning production backend engineering. The roadmap communicates
direction, not a guarantee of delivery dates.

## v1.0 — Production foundation

Status: released

- FastAPI application and PostgreSQL integration
- SQLAlchemy models and Alembic migrations
- Access and refresh token authentication
- Refresh token hashing, rotation, and revocation
- Role-based authorization
- Security headers, CORS, rate limiting, and request logging
- Health checks and exception handling
- Automated tests and GitHub Actions CI
- Deployment and community documentation

## v1.0.1 — Release readiness

Status: in progress

- Repair README and documentation rendering
- Align package, application, and release versions
- Validate the distributable wheel
- Run CI against PostgreSQL
- Enforce formatting, lint, and dependency auditing
- Update the supported Gunicorn/Uvicorn worker integration
- Standardize repository funding and contribution files

## v1.1 — Observability and developer experience

Status: in progress

- Structured JSON logging with request correlation IDs (completed)
- Prometheus-compatible application metrics (completed)
- OpenTelemetry tracing example
- Readiness and liveness semantics (completed)
- Expanded integration tests (completed)
- Improved local-development commands and examples (completed)
- API usage, architecture, and deployment examples (completed)

## v1.2 — Authentication lifecycle

Status: planned

- Email verification
- Password reset flow
- OAuth provider examples
- Multi-factor authentication foundation
- Session and device management

## v1.3 — Distributed workloads

Status: planned

- Redis-backed rate limiting
- Background task processing
- Caching patterns and invalidation guidance
- Async database evaluation and performance benchmarks
- Load-testing examples

## v2.0 — Deployment patterns at scale

Status: exploratory

- Container image and Compose development stack
- Kubernetes deployment example
- Cloud deployment guides
- Backup, disaster recovery, and operational runbooks
- Advanced policy and audit capabilities

## Contributing to the roadmap

Use GitHub Discussions to propose or validate larger ideas. Once the problem and
scope are clear, an issue can track implementation. Small issues labeled
`good first issue` or `help wanted` are the best entry points for contributors.
