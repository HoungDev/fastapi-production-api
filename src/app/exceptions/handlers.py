import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.request_context import REQUEST_ID_HEADER

logger = logging.getLogger("fastapi-production-api")


def _request_id_headers(request: Request) -> dict[str, str]:
    request_id = getattr(request.state, "request_id", None)
    return {REQUEST_ID_HEADER: request_id} if request_id else {}


def register_exception_handlers(
    app: FastAPI,
) -> None:

    @app.exception_handler(HTTPException)
    async def http_exception_handler(
        request: Request,
        exc: HTTPException,
    ):
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "detail": exc.detail,
            },
            headers=_request_id_headers(request),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request,
        exc: RequestValidationError,
    ):
        logger.warning(
            "Validation error: %s %s",
            request.method,
            request.url.path,
        )

        return JSONResponse(
            status_code=422,
            content={
                "detail": "Validation error",
            },
            headers=_request_id_headers(request),
        )

    @app.exception_handler(Exception)
    async def global_exception_handler(
        request: Request,
        exc: Exception,
    ):
        logger.exception(
            "Unhandled exception: %s %s",
            request.method,
            request.url.path,
        )

        return JSONResponse(
            status_code=500,
            content={
                "detail": "Internal Server Error",
            },
            headers=_request_id_headers(request),
        )
