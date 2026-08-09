import logging
import time

from fastapi import FastAPI, Request

from app.core.metrics import (
    HTTP_REQUEST_DURATION_SECONDS,
    HTTP_REQUESTS_IN_PROGRESS,
    HTTP_REQUESTS_TOTAL,
)
from app.core.request_context import (
    REQUEST_ID_HEADER,
    reset_request_id,
    resolve_request_id,
    set_request_id,
)

logger = logging.getLogger("fastapi-production-api.request")


def setup_request_logging(
    app: FastAPI,
) -> None:

    @app.middleware("http")
    async def request_logging_middleware(
        request: Request,
        call_next,
    ):
        request_id = resolve_request_id(request.headers.get(REQUEST_ID_HEADER))
        request.state.request_id = request_id
        context_token = set_request_id(request_id)
        start_time = time.perf_counter()
        method = request.method
        status_code = 500
        error: Exception | None = None
        HTTP_REQUESTS_IN_PROGRESS.labels(method=method).inc()

        try:
            response = await call_next(request)
            status_code = response.status_code
            response.headers[REQUEST_ID_HEADER] = request_id
            return response
        except Exception as exc:
            error = exc
            raise
        finally:
            duration_seconds = time.perf_counter() - start_time
            route = getattr(request.scope.get("route"), "path", "unmatched")

            HTTP_REQUESTS_IN_PROGRESS.labels(method=method).dec()
            HTTP_REQUESTS_TOTAL.labels(
                method=method,
                route=route,
                status_code=str(status_code),
            ).inc()
            HTTP_REQUEST_DURATION_SECONDS.labels(
                method=method,
                route=route,
            ).observe(duration_seconds)

            level = logging.INFO
            if status_code >= 500:
                level = logging.ERROR
            elif status_code >= 400:
                level = logging.WARNING

            logger.log(
                level,
                "http_request",
                extra={
                    "method": method,
                    "path": request.url.path,
                    "route": route,
                    "status_code": status_code,
                    "duration_ms": round(duration_seconds * 1000, 2),
                },
                exc_info=error,
            )
            reset_request_id(context_token)
