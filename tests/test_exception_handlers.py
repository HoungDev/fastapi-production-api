from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.exceptions.handlers import register_exception_handlers


def create_exception_test_app() -> FastAPI:
    test_app = FastAPI()
    register_exception_handlers(test_app)

    @test_app.middleware("http")
    async def add_request_id(request, call_next):
        request.state.request_id = "exception-test-request"
        return await call_next(request)

    @test_app.get("/http-error")
    def http_error():
        raise HTTPException(status_code=409, detail="Conflict")

    @test_app.get("/unexpected-error")
    def unexpected_error():
        raise RuntimeError("sensitive internal detail")

    @test_app.get("/validated/{item_id}")
    def validated(item_id: int):
        return {"item_id": item_id}

    return test_app


def test_http_exception_preserves_safe_detail():
    client = TestClient(create_exception_test_app())

    response = client.get("/http-error")

    assert response.status_code == 409
    assert response.json() == {"detail": "Conflict"}
    assert response.headers["X-Request-ID"] == "exception-test-request"


def test_validation_error_uses_consistent_response():
    client = TestClient(create_exception_test_app())

    response = client.get("/validated/not-an-integer")

    assert response.status_code == 422
    assert response.json() == {"detail": "Validation error"}
    assert response.headers["X-Request-ID"] == "exception-test-request"


def test_unexpected_error_does_not_leak_internal_detail():
    client = TestClient(
        create_exception_test_app(),
        raise_server_exceptions=False,
    )

    response = client.get("/unexpected-error")

    assert response.status_code == 500
    assert response.json() == {"detail": "Internal Server Error"}
    assert "sensitive internal detail" not in response.text
    assert response.headers["X-Request-ID"] == "exception-test-request"
