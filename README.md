# FastAPI Production API

A production-ready REST API built with FastAPI, PostgreSQL, authentication, testing, and Docker.

## Features

- FastAPI framework
- JWT Authentication
- OAuth2 Password Bearer
- Environment-based configuration
- Automated testing with Pytest
- Application logging

## Project Structure

```text
src/
app/
    api/
    auth/
    core/
    db/
    models/
    repositories/
    schemas/
    services/
    main.py
```

## Installation

Install dependencies:

```bash
uv sync
```

## Environment

Create `.env` file:

```env
APP_NAME=FastAPI Production API
DATABASE_URL=sqlite:///app.db

SECRET_KEY=your-secret-key
ALGORITHM=HS256

ACCESS_TOKEN_EXPIRE_MINUTES=30

JWT_AUDIENCE=fastapi-client
JWT_ISSUER=fastapi-production-api
```

## Run Application

Start server:

```bash
python -m uvicorn app.main:app --reload
```

Application:

```text
http://127.0.0.1:8000
```

Swagger Documentation:

```text
http://127.0.0.1:8000/docs
```

## Authentication Flow

### Register

```text
POST /register/
```

### Login

```text
POST /login/
```

### Protected Routes

```text
GET /auth/me
GET /me
```

## Testing

Run tests:

```bash
python -m pytest
```

Current status:

```text
32 passed
```

## License

MIT License