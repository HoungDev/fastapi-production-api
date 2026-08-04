from fastapi import FastAPI, Request


def setup_security_headers(
    app: FastAPI,
) -> None:

    @app.middleware("http")
    async def security_headers_middleware(
        request: Request,
        call_next,
    ):
        response = await call_next(request)

        response.headers["X-Content-Type-Options"] = "nosniff"

        response.headers["X-Frame-Options"] = "DENY"

        response.headers["X-XSS-Protection"] = "1; mode=block"

        response.headers["Referrer-Policy"] = (
            "strict-origin-when-cross-origin"
        )

        return response