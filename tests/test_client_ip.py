from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from app.core.client_ip import resolve_client_ip


def _request(client_host: str | None) -> Request:
    client = (client_host, 12345) if client_host is not None else None
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": [],
            "client": client,
            "server": ("testserver", 80),
            "scheme": "http",
            "query_string": b"",
        }
    )


def test_client_ip_is_canonicalized():
    assert resolve_client_ip(_request("2001:0db8:0:0:0:0:0:1")) == "2001:db8::1"
    assert resolve_client_ip(_request("::ffff:192.0.2.10")) == "192.0.2.10"


def test_missing_or_non_ip_client_fails_to_one_bounded_identity():
    assert resolve_client_ip(_request(None)) == "unknown"
    assert resolve_client_ip(_request("attacker-controlled-value")) == "unknown"
    assert resolve_client_ip(_request("1" * 1024)) == "unknown"


def _proxy_test_client(*, socket_peer: str, trusted_hosts: str) -> TestClient:
    inner_app = FastAPI()

    @inner_app.get("/")
    def client_address(request: Request):
        return {"client_ip": resolve_client_ip(request)}

    app = ProxyHeadersMiddleware(inner_app, trusted_hosts=trusted_hosts)
    return TestClient(app, client=(socket_peer, 12345))


def test_untrusted_socket_peer_cannot_spoof_forwarded_client_ip():
    client = _proxy_test_client(
        socket_peer="192.0.2.10",
        trusted_hosts="10.0.0.0/8",
    )

    response = client.get("/", headers={"X-Forwarded-For": "203.0.113.99"})

    assert response.json() == {"client_ip": "192.0.2.10"}


def test_trusted_proxy_chain_uses_nearest_untrusted_address():
    client = _proxy_test_client(
        socket_peer="10.0.0.3",
        trusted_hosts="10.0.0.0/8",
    )

    response = client.get(
        "/",
        headers={"X-Forwarded-For": "203.0.113.99, 198.51.100.20, 10.0.0.2"},
    )

    assert response.json() == {"client_ip": "198.51.100.20"}


def test_malformed_forwarded_address_fails_to_unknown_identity():
    client = _proxy_test_client(
        socket_peer="10.0.0.3",
        trusted_hosts="10.0.0.0/8",
    )

    response = client.get("/", headers={"X-Forwarded-For": "not-an-ip"})

    assert response.json() == {"client_ip": "unknown"}
