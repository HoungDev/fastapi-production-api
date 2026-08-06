# FastAPI Production API

[![CI](https://github.com/HoungDev/fastapi-production-api/actions/workflows/ci.yml/badge.svg)](https://github.com/HoungDev/fastapi-production-api/actions)
[![Python](https://img.shields.io/badge/Python-3.12-blue.svg)]()
[![FastAPI](https://img.shields.io/badge/FastAPI-Production-green.svg)]()
[![License](https://img.shields.io/badge/License-MIT-blue.svg)]()

A production-ready FastAPI backend template designed for building secure, scalable, and maintainable APIs.

Built with:

- FastAPI
- PostgreSQL
- SQLAlchemy ORM
- Alembic migrations
- JWT Authentication
- Automated testing
- Docker
- GitHub Actions CI/CD

Maintained by **HoungDev**.

This project provides a production-focused backend foundation with clean architecture, security best practices, and developer-friendly workflows.

---

## 💗 Support Open Source Development

FastAPI Production API is an open-source project maintained by **HoungDev**.

Maintaining a production-ready backend template requires continuous work including:

- 🔒 Security updates and dependency maintenance
- 🧪 Improving automated tests and reliability
- 📚 Maintaining documentation and examples
- 🚀 Adding new features and developer improvements

If this project helps you build better FastAPI applications, you can support the project by:

- ⭐ Starring the repository
- 🐛 Reporting issues
- 💡 Suggesting improvements
- 🤝 Contributing code
- 💗 Becoming a GitHub Sponsor

Every contribution helps keep this project actively maintained and improved.

Thank you for supporting open-source software.

## 🛠️ Tech Stack

### Backend
- ⚡ **FastAPI** - Modern Python web framework for building APIs
- 🐘 **PostgreSQL** - Reliable relational database
- 🔗 **SQLAlchemy ORM** - Database abstraction layer
- 🗃️ **Alembic** - Database migration management
- 🔐 **JWT Authentication** - Secure authentication system

### Development & Quality
- 🐍 **Python 3.12**
- 🧪 **Pytest** - Automated testing
- 🐳 **Docker** - Containerized development and deployment
- ⚙️ **GitHub Actions** - CI/CD automation

### Production
- 🚀 Production-ready configuration
- 🔒 Security-focused architecture
- 📦 Environment-based configuration
- 📖 Developer-friendly documentation
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
- Database transaction rollback safety
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

## Project Structure

```text
fastapi-production-api/
│
├── .github/                    # GitHub workflows and repository configuration
│
├── src/                        # Application source code
│
├── tests/                      # Automated test suite
│
├── alembic/                    # Database migration scripts
│
├── docker-compose.yml          # Container configuration
├── gunicorn.conf.py            # Production server configuration
├── alembic.ini                 # Alembic configuration
│
├── pyproject.toml              # Project dependencies and metadata
├── uv.lock                     # Locked dependency versions
│
├── .env.example                # Environment template
│
├── README.md
├── CHANGELOG.md
├── ROADMAP.md
├── DEPLOYMENT.md
├── SECURITY.md
├── CONTRIBUTING.md
├── CODE_OF_CONDUCT.md
└── LICENSE
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

Create migration:

```bash
uv run alembic revision --autogenerate -m "migration message"
```

---

# Development Server

Run:

```bash
uv run uvicorn src.app.main:app --reload
```

Server:

```
http://localhost:8000
```

Swagger:

```
http://localhost:8000/docs
```

ReDoc:

```
http://localhost:8000/redoc
```

---

# Production Server

Production deployment uses Gunicorn with Uvicorn workers.

Run:

```bash
uv run gunicorn \
-c gunicorn.conf.py \
src.app.main:app
```

Architecture:

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

Run:

```bash
uv run pytest
```

Current test status:

```
34 passed
```

Coverage includes:

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
Setup Python
        |
Install uv
        |
Install dependencies
        |
Run migrations
        |
Run tests
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
- JWT issuer validation
- JWT audience validation
- Refresh token hashing
- Refresh token rotation
- Refresh token revocation
- Rate limiting
- Security headers
- Exception isolation
- Database transaction rollback

---

# Open Source

This project is built with the goal of helping developers learn and build secure FastAPI backend systems.

Contributions are welcome.

Please read:

- [CONTRIBUTING.md](CONTRIBUTING.md)
- [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)
- [ROADMAP.md](ROADMAP.md)

---

# Maintainer

Maintained by:

**HoungDev**

Open Source Maintainer focused on:

- Python backend development
- FastAPI architecture
- API security
- Production engineering

---

# Production Status

Current release:

```
v1.0.0
```

Completed:

✅ Authentication system

✅ JWT security

✅ Refresh token rotation

✅ Database migrations

✅ Automated testing

✅ CI/CD pipeline

✅ Security middleware

✅ Logging system

---

# Roadmap

Future improvements:

- Redis integration
- Background task processing
- Monitoring system
- Metrics collection
- Cloud deployment examples
- Improved developer experience

See:

```
ROADMAP.md
```

---

# Community

Contributions and discussions are welcome.

Please check:

- Issues
- Pull Requests
- Feature Requests
- Discussions

---

# License

MIT License
