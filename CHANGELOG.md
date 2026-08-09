# Changelog

All notable changes to this project are documented in this file. The format is
based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the
project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Optional normalized email identities during backward-compatible registration
- Single-use, hashed, expiring account-action tokens for email verification
- Enumeration-resistant verification request and atomic confirmation endpoints
- Explicit disabled/SMTP delivery boundary and verification configuration
- Enumeration-resistant password recovery with scoped, hashed reset tokens
- Atomic password updates with refresh-session revocation
- Refresh-token families with rotation-replay detection
- Authenticated device-session listing and idempotent family revocation

### Changed

- Registration conflicts now return a controlled `409` response
- SMTP delivery supports separately configured verification and reset URLs
- Login accepts a bounded device label and logout revokes the full token family

## [1.1.0] - 2026-08-09

### Added

- Dedicated liveness and database-backed readiness probes
- Prometheus request count, status, latency, and in-progress metrics
- Structured JSON logs with validated request correlation IDs
- Monitoring, alerting, multi-worker metrics, and troubleshooting guidance
- Branch-aware test coverage reporting with a 90% CI gate and XML artifact
- Expanded admin, CORS, exception, rollback, refresh-token, and rate-limit tests
- Cross-platform setup, database, server, migration, and quality-gate commands
- Local development workflow and troubleshooting guide
- Copy-paste API authentication, authorization, health, and metrics examples
- Architecture guide covering request flow, security, data, and observability
- Deployment-pattern and safe release-sequence guidance
- Automated validation for internal documentation links

## [1.0.1] - 2026-08-08

### Added

- Ruff linting and formatting checks
- Dependency auditing as an enforced CI gate
- PostgreSQL 17 service for migrations and tests in CI
- Wheel build and import smoke test
- Package URLs, classifiers, and release metadata
- Explicit current limitations and a release checklist

### Changed

- Prepared package version 1.0.1
- Reworked README around value, quick start, architecture, and evidence
- Replaced deprecated `uvicorn.workers.UvicornWorker` with `uvicorn-worker`
- Replaced the deprecated `httpx` test dependency with `httpx2`
- Replaced Passlib's unmaintained bcrypt adapter with direct bcrypt calls while
  retaining compatibility with existing bcrypt hashes
- Updated contribution, deployment, and roadmap documentation
- Moved funding configuration to `.github/FUNDING.yml`

### Fixed

- Closed the README project-structure code block that hid subsequent sections
- Aligned the documented Python requirement with Python 3.13
- Included the `app` package in built wheel artifacts
- Removed hard-coded application version strings
- Removed a CI security-audit command that could silently succeed after failure

## [1.0.0] - 2026-08-05

### Added

- FastAPI application architecture
- PostgreSQL database integration with SQLAlchemy and Alembic
- JWT access-token authentication
- Hashed refresh tokens with rotation and revocation
- bcrypt password hashing
- Role-based authorization
- CORS, security headers, rate limiting, and request logging
- Health checks and global exception handling
- Authentication and token-security test suite
- GitHub Actions CI
- Initial deployment and community documentation

[Unreleased]: https://github.com/HoungDev/fastapi-production-api/compare/v1.1.0...HEAD
[1.1.0]: https://github.com/HoungDev/fastapi-production-api/compare/v1.0.1...v1.1.0
[1.0.1]: https://github.com/HoungDev/fastapi-production-api/compare/v1.0.0...v1.0.1
[1.0.0]: https://github.com/HoungDev/fastapi-production-api/releases/tag/v1.0.0
