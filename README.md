# FastAPI Production API

A production-ready REST API built with FastAPI, PostgreSQL, JWT authentication, automated testing, and CI/CD.

## Features

- FastAPI framework
- PostgreSQL database
- SQLAlchemy ORM
- Alembic database migrations
- JWT Authentication
- OAuth2 Password Bearer
- Access Token + Refresh Token
- Role-based user authorization
- Environment-based configuration
- Application logging
- Database health monitoring
- Automated testing with Pytest
- GitHub Actions CI

---

## Project Structure

src/
|
+-- app/
|   |
|   +-- api/
|   |   +-- v1/
|   |
|   +-- auth/
|   +-- core/
|   +-- db/
|   +-- models/
|   +-- repositories/
|   +-- schemas/
|   +-- services/
|   +-- main.py

alembic/
tests/
gunicorn.conf.py
pyproject.toml
uv.lock