import time
from typing import Dict, List

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


class RateLimiter:
    def __init__(
        self,
        limit: int = 100,
        window: int = 60,
    ):
        self.limit = limit
        self.window = window
        self.requests: Dict[str, List[float]] = {}


    def is_allowed(
        self,
        client_ip: str,
    ) -> bool:

        current_time = time.time()

        if client_ip not in self.requests:
            self.requests[client_ip] = []


        self.requests[client_ip] = [
            timestamp
            for timestamp in self.requests[client_ip]
            if current_time - timestamp < self.window
        ]


        if len(self.requests[client_ip]) >= self.limit:
            return False


        self.requests[client_ip].append(
            current_time
        )

        return True



rate_limiter = RateLimiter(
    limit=100,
    window=60,
)



def setup_rate_limit(
    app: FastAPI,
) -> None:

    @app.middleware("http")
    async def rate_limit_middleware(
        request: Request,
        call_next,
    ):

        client_ip = (
            request.client.host
            if request.client
            else "unknown"
        )


        if not rate_limiter.is_allowed(
            client_ip
        ):
            return JSONResponse(
                status_code=429,
                content={
                    "detail": "Too many requests",
                },
            )


        response = await call_next(
            request
        )

        return response