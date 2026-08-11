import ipaddress

from fastapi import Request


def resolve_client_ip(request: Request) -> str:
    """Return the canonical IP address already resolved by the ASGI server."""
    if request.client is None:
        return "unknown"

    if len(request.client.host) > 45:
        return "unknown"

    try:
        address = ipaddress.ip_address(request.client.host)
    except ValueError:
        return "unknown"

    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
        return address.ipv4_mapped.compressed

    return address.compressed
