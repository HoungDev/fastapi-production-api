from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("fastapi-production-api")
except PackageNotFoundError:  # pragma: no cover - source tree fallback
    __version__ = "0.0.0"


def main() -> None:
    """Run the API with safe single-process defaults."""
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        log_level="info",
    )
