import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


logger = logging.getLogger(
    "fastapi-production-api"
)


def register_exception_handlers(
    app: FastAPI,
) -> None:

    @app.exception_handler(Exception)
    async def global_exception_handler(
        request: Request,
        exc: Exception,
    ):
        logger.exception(
            "Unhandled exception: %s %s",
            request.method,
            request.url,
            exc_info=exc,
        )

        return JSONResponse(
            status_code=500,
            content={
                "detail": "Internal Server Error",
            },
        )