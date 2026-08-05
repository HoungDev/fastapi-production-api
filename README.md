# FastAPI Production API

A production-ready REST API built with **FastAPI**, **PostgreSQL**, **SQLAlchemy**, **Alembic**, **JWT Authentication**, automated testing, and GitHub Actions CI/CD.

---

# Features

## Backend

- FastAPI framework
- PostgreSQL database
- SQLAlchemy ORM
- Alembic database migrations
- Pydantic Settings configuration
- Gunicorn + Uvicorn production server


## Authentication & Security

- JWT Authentication
- OAuth2 Password Bearer authentication
- Access Token authentication
- Refresh Token authentication
- Refresh Token hashing
- Refresh Token rotation
- Refresh Token revocation
- bcrypt password hashing
- JWT issuer validation
- JWT audience validation
- Role-based authorization


## Middleware

- CORS configuration
- Security headers middleware
- Rate limiting middleware
- Request logging middleware


## Reliability

- Database health check
- Global exception handling
- Transaction rollback safety
- Environment-based configuration


## Testing & CI/CD

- Pytest automated testing
- Authentication tests
- JWT security tests
- Refresh token rotation tests
- Rate limit tests
- GitHub Actions CI pipeline
- Dependency security audit

---

# Project Structure

```
fastapi-production-api/

├── src/
│   └── app/
│       ├── api/
│       │   └── v1/
│       │
│       ├── auth/
│       │
│       ├── core/
│       │
│       ├── db/
│       │
│       ├── exceptions/
│       │
│       ├── middlewares/
│       │
│       ├── models/
│       │
│       ├── schemas/
│       │
│       └── main.py
│
├── alembic/
│
├── tests/
│
├── .github/
│   └── workflows/
│
├── gunicorn.conf.py
├── pyproject.toml
├── uv.lock
├── .env.example
└── README.md
```

---

# Requirements

- Python 3.13+
- PostgreSQL
- uv package manager

---

# Installation

Clone repository:

```bash
git clone https://github.com/HoungDev/fastapi-production-api.git

cd fastapi-production-api
```

Install dependencies:

```bash
uv sync
```

---

# Environment Configuration

Create environment file:

```bash
cp .env.example .env
```

Example:

```env
APP_NAME=FastAPI Production API

ENVIRONMENT=development

DEBUG=false

LOG_LEVEL=INFO

DATABASE_URL=postgresql+psycopg://user:password@localhost:5432/database

SECRET_KEY=your-secret-key

ALGORITHM=HS256

ACCESS_TOKEN_EXPIRE_MINUTES=30

REFRESH_TOKEN_EXPIRE_DAYS=7
```

---

# Database Migration

Run migrations:

```bash
uv run alembic upgrade head
```

Create new migration:

```bash
uv run alembic revision --autogenerate -m "migration message"
```

---

# Run Development Server

Start API:

```bash
uv run uvicorn src.app.main:app --reload
```

Server:

```
http://localhost:8000
```

Swagger documentation:

```
http://localhost:8000/docs
```

ReDoc:

```
http://localhost:8000/redoc
```

---

# Run Production Server

Production uses Gunicorn with Uvicorn workers.

Start:

```bash
uv run gunicorn \
-c gunicorn.conf.py \
src.app.main:app
```

Production architecture:

```
Nginx
  |
Gunicorn
  |
FastAPI
  |
PostgreSQL
```

---

# Testing

Run all tests:

```bash
uv run pytest
```

Test coverage includes:

```
Authentication
├── Register
├── Login
├── JWT validation
├── Protected routes
└── Current user


Token Security
├── Access token
├── Refresh token
├── Token expiration
├── Token issuer
├── Token audience
└── Refresh rotation


System
├── Health check
├── Rate limiting
└── Exception handling
```

---

# CI/CD Pipeline

GitHub Actions runs automatically on:

- Push to main branch
- Pull requests to main branch


Pipeline:

```
Checkout repository
        |
Setup Python 3.13
        |
Install uv
        |
Install dependencies
        |
Run database migration
        |
Run pytest
        |
Security audit
```

---

# API Endpoints

## Health

```
GET /health
```

Database health:

```
GET /health/db
```


## Authentication

Register:

```
POST /register/
```

Login:

```
POST /login/
```

Refresh token:

```
POST /auth/refresh
```

Logout:

```
POST /auth/logout
```


## User

Current user:

```
GET /auth/me
```

---

# Security Implementation

Implemented security features:

- Password hashing with bcrypt
- JWT authentication
- JWT issuer checking
- JWT audience checking
- Refresh token hashing
- Refresh token rotation
- Refresh token revocation
- Rate limiting
- Security headers
- Exception isolation
- Database transaction rollback

---

# Production Checklist

Completed:

[x] Authentication system

[x] JWT security

[x] Refresh token rotation

[x] Database migrations

[x] Automated testing

[x] CI/CD pipeline

[x] Logging middleware

[x] Security middleware

[x] Error handling


Future improvements:

- Nginx deployment
- SSL certificate automation
- Monitoring system
- Metrics collection
- Database backup automation

---

# License

MIT License
