\# Contributing Guide



Thank you for your interest in contributing to FastAPI Production API.



This project welcomes developers who want to improve backend engineering practices, security, testing, and production-ready FastAPI development.



\---



\# Development Setup



\## Requirements



\- Python 3.13+

\- uv

\- PostgreSQL





\## Install project



Clone repository:



```bash

git clone https://github.com/HoungDev/fastapi-production-api.git



cd fastapi-production-api

```



Install dependencies:



```bash

uv sync

```



\---



\# Running Tests



Before submitting changes, run:



```bash

uv run pytest

```



All tests should pass.



\---



\# Code Guidelines



Please follow:



\- Clean Python code

\- Type hints

\- Clear naming

\- Small focused commits

\- Add tests for new features





\---



\# Pull Request Process



Before opening a pull request:



1\. Create a new branch



```bash

git checkout -b feature/my-feature

```





2\. Make your changes





3\. Run tests



```bash

uv run pytest

```





4\. Commit changes



Example:



```bash

git commit -m "Add new authentication feature"

```





5\. Push branch and create Pull Request





\---



\# Commit Convention



Recommended format:



```

type: description

```



Examples:



```

feat: add OAuth login



fix: handle expired refresh token



docs: update deployment guide



test: add authentication tests

```



\---



\# Reporting Bugs



Please include:



\- Operating system

\- Python version

\- Steps to reproduce

\- Expected behavior

\- Actual behavior





\---



\# Feature Requests



Feature requests are welcome.



Please explain:



\- The problem

\- Proposed solution

\- Why this improves the project





\---



\# Security Issues



Do not open public issues for security vulnerabilities.



Please contact the maintainer privately.



