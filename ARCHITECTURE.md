# Architecture guide

FastAPI Production API is a synchronous, layered reference application. It
keeps HTTP concerns, authentication, persistence, and operations separate so a
team can replace one part without rewriting the entire service.

## System context

```mermaid
flowchart LR
    Client["API client"] --> Proxy["Trusted reverse proxy / TLS"]
    Proxy --> App["FastAPI application"]
    App --> Auth["JWT, refresh tokens, and RBAC"]
    App --> DB[("PostgreSQL")]
    App --> Redis[("Redis quotas")]
    App --> Outbox[("PostgreSQL outbox")]
    Worker["Outbox workers"] --> Outbox
    Worker --> SMTP
    App --> SMTP["SMTP email provider"]
    App --> Logs["Structured JSON logs"]
    Prometheus["Prometheus"] --> Metrics["/metrics"]
    Metrics --> App
```

The reverse proxy terminates TLS and controls trusted forwarding headers. The
application owns validation, authorization, business transactions, and
telemetry. PostgreSQL is required; Redis becomes a required readiness dependency
when distributed rate limiting is enabled.

## Source layout and responsibilities

| Area | Path | Responsibility |
| --- | --- | --- |
| Application assembly | `src/app/main.py` | Create FastAPI, register middleware and handlers, include routers |
| HTTP routes | `src/app/api/v1/` | Parse requests, enforce dependencies, return response models |
| Authentication | `src/app/auth/` | Password verification, JWT validation, refresh rotation, permissions |
| Configuration | `src/app/core/` | Environment settings, Redis lifecycle, logging, metrics, request context |
| Persistence | `src/app/db/`, `src/app/models/`, `src/app/repositories/` | Sessions, ORM models, and data access |
| Contracts | `src/app/schemas/` | Pydantic request and response models |
| Cross-cutting HTTP behavior | `src/app/middlewares/` | CORS, headers, rate limiting, request logging |
| Durable work | `src/app/services/outbox.py`, `src/app/services/outbox_worker.py` | Atomic enqueue, encryption, leasing, retries, and terminal handling |
| Error boundary | `src/app/exceptions/` | Stable client errors and safe unexpected-error responses |
| Schema evolution | `alembic/` | Ordered PostgreSQL migrations |
| Verification | `tests/` | Endpoint, security, failure-path, and operational tests |
| Database evaluation | `benchmarks/` | Opt-in sync baseline and isolated async prototype; never imported by production startup |

Routers should remain thin: validate input, compose dependencies and services,
and translate results into HTTP responses. Reusable authentication or database
behavior belongs outside route modules.

## Request lifecycle

```mermaid
sequenceDiagram
    participant C as Client
    participant M as Middleware
    participant R as Router / dependencies
    participant A as Auth and services
    participant D as Database

    C->>M: HTTP request + optional X-Request-ID
    M->>M: CORS, security headers, rate limit, request context
    M->>R: Validated request
    R->>A: Authentication and operation
    A->>D: Query or transaction
    D-->>A: Result
    A-->>R: Domain result
    R-->>M: HTTP response
    M->>M: Metrics and structured completion log
    M-->>C: Response + X-Request-ID
```

Global exception handlers keep validation, HTTP, and unexpected failures
consistent. Unexpected exceptions are logged with their correlation ID while
the response omits internal details.

## Authentication lifecycle

1. `POST /register/` hashes the password with bcrypt before committing a user.
2. `POST /login/` verifies the password, creates a short-lived JWT access token,
   creates an opaque refresh token, and stores only the refresh-token hash.
3. Protected routes decode the JWT and validate algorithm, issuer, audience,
   expiration, token type, and subject. The current user is then loaded from the
   database, so deleted users and role changes take effect without waiting for a
   new access token.
4. `POST /auth/refresh` validates the stored token, rejects revoked or expired
   records, locks and revokes the old token, and commits a replacement in the
   same server-generated family. Replay of a rotated token revokes the family's
   live descendant.
5. `POST /auth/logout` revokes the submitted refresh-token family.
6. Registration may attach a normalized email identity. Verification requests
   invalidate older outstanding tokens, persist only a SHA-256 token hash, and
   deliver the raw token through the configured SMTP boundary.
7. Confirmation locks and atomically consumes the scoped token while setting
   `email_verified_at`. Expiry, replay, purpose, and current-email checks occur
   before the transaction commits.
8. Password-reset requests reuse the account-action token table with a distinct
   purpose and only accept active, verified email identities without revealing
   eligibility to the caller.
9. Reset confirmation locks both token and user, updates the password hash,
   consumes outstanding reset tokens, and revokes every refresh token in one
   transaction. It creates no replacement session.
10. Authenticated session endpoints aggregate active refresh-token families and
    allow idempotent revocation of one or all families while filtering every
    operation by current user ownership.
11. TOTP enrollment encrypts the authenticator seed with a dedicated Fernet
    key. Confirmation stores only hashes of newly generated recovery codes.
12. Login for an MFA-enabled account returns a short-lived, opaque challenge
    instead of session tokens. Successful TOTP or recovery verification consumes
    the challenge and creates the device session in one transaction.
13. Accepted TOTP counters are recorded to reject replay in the same time step.
    Access tokens record authentication methods (`amr`) and time (`auth_time`);
    refresh-issued access tokens use `amr=["refresh"]` and cannot satisfy recent
    MFA step-up checks.
14. OIDC authorization creates a short-lived database transaction containing
    hashes of `state`, nonce, and browser binding plus an encrypted PKCE verifier.
    The authorization request always uses Authorization Code and PKCE S256.
15. The callback validates browser binding, discovery issuer, ID-token signature,
    algorithm, issuer, audience, authorized party, lifetime, subject, and nonce
    before consuming the transaction and issuing a local device session.
16. External identities use immutable `(issuer, subject)` keys. Matching email
    never links an existing account; linking requires a recent authenticated
    local session. Identity changes revoke refresh sessions.
17. Optional Redis cache-aside stores only validated public OIDC discovery and
    JWKS documents under versioned issuer-digest keys. Every cache read is
    validated again. Misses use a bounded refresh lock; Redis errors bypass to
    the provider. An unknown cached `kid` forces one provider JWKS refresh.

Refresh-token families detect replay and make device-level revocation possible.
Access tokens are stateless and remain valid until expiration, so clients must
discard them on logout and deployments must protect the signing secret.

## Authorization model

Authentication answers who the user is; authorization decides what that user
may do. Admin routes call the centralized permission check after resolving the
current database user. New roles or permissions should be added centrally and
covered by both allow and deny tests.

## Data and transaction boundaries

Each request receives a SQLAlchemy session through a FastAPI dependency. Write
operations explicitly commit only after all required mutations are ready and
roll back when persistence fails. Alembic migrations are the source of truth
for schema changes.

Production releases should run migrations once before starting new application
workers. Do not let every worker race to apply schema changes.

The production persistence path remains synchronous for v1.3.0. The asyncpg
engine under `benchmarks/` exists only for controlled comparison and preserves
equivalent SQL and transaction boundaries. It is not an alternate application
dependency. See [DATABASE_BENCHMARKS.md](DATABASE_BENCHMARKS.md) and
[ADR 0001](docs/decisions/0001-keep-sync-sqlalchemy.md) for the evidence gate
and decision rationale.

In transactional delivery mode, the lifecycle token and encrypted outbox row
commit together. Workers claim due rows in short `FOR UPDATE SKIP LOCKED`
transactions, commit leases before SMTP I/O, and condition finalization on the
lease owner. Expired leases are recoverable. SMTP remains an external
at-least-once boundary, so duplicate delivery is possible after ambiguous
provider acceptance. Success and dead-letter transitions purge encrypted
payloads.

## Observability model

- `/health/live` reports process liveness without dependency checks.
- `/health/ready` verifies PostgreSQL and, when configured, Redis connectivity
  before accepting traffic.
- `/metrics` exports bounded-label request count, status, latency, and
  in-progress metrics.
- JSON request logs carry method, normalized path, status, duration, and a
  validated correlation ID.
- Rate-limit metrics use only bounded backend, outcome, and operation labels.
- Outbox metrics use bounded message types, outcomes, and failure categories;
  worker logs never include recipients, tokens, ciphertext, or provider details.
- OIDC cache/provider metrics use only bounded document and outcome labels;
  issuer URLs, key IDs, documents, tokens, and credentials are excluded.

Read [MONITORING.md](MONITORING.md) for scrape configuration, multi-worker
metrics, alerts, and troubleshooting.

## Trace propagation boundary

Tracing is disabled by default. When enabled, the application uses W3C Trace
Context across supported request and worker boundaries.

Transactional outbox rows persist only bounded `traceparent` and `tracestate`
fields so a worker can continue the originating trace after the enqueue
transaction has committed.

Trace metadata remains separate from the encrypted lifecycle payload. Retryable
jobs retain trace context so later attempts remain correlated; successful and
dead-letter jobs purge the stored trace metadata.

Malformed or oversized propagation values are ignored safely. W3C baggage is
not persisted through the outbox.

Tracing must not change leasing, idempotency, retry behavior, transaction
correctness, SMTP delivery semantics, readiness, or application availability.

## Configuration and trust boundaries

Settings come from environment variables and `.env`; process environment values
take precedence. Production validation rejects debug mode and short or known
placeholder secrets. SMTP delivery is opt-in and requires a host and sender;
disabled delivery does not create unreachable tokens. MFA and OIDC transaction
data use dedicated encryption keys rather than the JWT signing secret. Redis
quota keys contain only versioned HMAC identifiers and bounded fixed-window
counters. OIDC cache keys contain a fixed issuer digest, document kind, and
bounded TTL; values contain only public discovery/JWKS JSON. CORS origins, proxy
trust, metrics exposure, database permissions, and secret storage remain
deployment responsibilities.

## Safe extension points

- Add a route in `src/app/api/v1/` and register its router in `main.py`.
- Put new request and response contracts in `src/app/schemas/`.
- Isolate reusable business rules in services and data access in repositories.
- Create an Alembic revision for every schema change.
- Add success, authorization, validation, rollback, and edge-case tests.
- Add low-cardinality metrics; never use usernames, IDs, or raw URLs as metric
  labels.

Run `python scripts/dev.py check` before review.

## Intentional limitations

Memory rate limiting remains available for single-process use; shared quotas
require Redis. Redis Cluster and cross-region quota guarantees are not included.
Refresh-token persistence and SMTP delivery are synchronous, and the repository
does not include phishing-resistant MFA, immediate JWT revocation, a
general-purpose application cache, or a production container image. Password
reset revokes refresh tokens, but existing stateless access tokens remain valid
until expiry. SMTP acceptance is not a durable delivery guarantee; applications
requiring that guarantee should add a transactional outbox and worker. These
are explicit roadmap items rather than hidden production claims. See
[ROADMAP.md](ROADMAP.md) and [DEPLOYMENT.md](DEPLOYMENT.md) before adopting the
foundation.
