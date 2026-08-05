import time
import logging

from fastapi import FastAPI, Request


logger = logging.getLogger(
    "fastapi-production-api.request"
)


def setup_request_logging(
    app: FastAPI,
) -> None:

    @app.middleware("http")
    async def request_logging_middleware(
        request: Request,
        call_next,
    ):

        start_time = time.perf_counter()

        response = await call_next(
            request
        )

        process_time = (
            time.perf_counter()
            - start_time
        ) * 1000

        logger.info(
            "%s %s %s %.2fms",
            request.method,
            request.url.path,
            response.status_code,
            process_time,
        )

        return response