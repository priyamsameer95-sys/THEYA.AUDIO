"""SSRF guard: only fetch public http(s) URLs.

The server fetches whatever URL a user pastes, so without this check a page
could make us fetch ``http://192.168.1.1/admin`` or cloud metadata at
``169.254.169.254``. Every hop (including each redirect) must pass
:func:`check_url` before any request is sent.

Known limitation: the hostname is resolved here and again by HTTPX, so a
hostile DNS server could rebind between the two lookups. That's acceptable
for a localhost-only tool. Pin resolved IPs before hosting publicly.
"""
from __future__ import annotations

import asyncio
import ipaddress
import socket
from typing import Awaitable, Callable, List, Optional
from urllib.parse import urlsplit

from app.extract.models import UnsafeURLError

ALLOWED_SCHEMES = frozenset({"http", "https"})

# (host, port) -> list of IP strings. Injectable so tests never touch DNS.
Resolver = Callable[[str, int], Awaitable[List[str]]]


async def system_resolver(host: str, port: int) -> List[str]:
    loop = asyncio.get_running_loop()
    try:
        infos = await loop.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise UnsafeURLError(f"Could not resolve host '{host}'.") from exc
    return sorted({info[4][0] for info in infos})


def is_public_ip(raw_ip: str) -> bool:
    """True only for globally routable unicast addresses."""
    ip = ipaddress.ip_address(raw_ip.split("%", 1)[0])  # drop IPv6 zone id
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped  # ::ffff:127.0.0.1 is really loopback
    return ip.is_global and not ip.is_multicast


def validate_url_syntax(url: str) -> tuple:
    """Return (scheme, host, port) or raise :class:`UnsafeURLError`."""
    try:
        parts = urlsplit(url.strip())
        port = parts.port
    except ValueError as exc:
        raise UnsafeURLError("That doesn't look like a valid URL.") from exc

    scheme = parts.scheme.lower()
    if scheme not in ALLOWED_SCHEMES:
        raise UnsafeURLError("Only http:// and https:// links are supported.")
    if parts.username or parts.password:
        raise UnsafeURLError("URLs with embedded credentials are not allowed.")
    host = parts.hostname
    if not host:
        raise UnsafeURLError("The URL is missing a hostname.")
    if port is None:
        port = 443 if scheme == "https" else 80
    return scheme, host, port


async def check_url(url: str, resolver: Optional[Resolver] = None) -> None:
    """Raise :class:`UnsafeURLError` unless every resolved IP is public."""
    _, host, port = validate_url_syntax(url)
    ips = await (resolver or system_resolver)(host, port)
    if not ips:
        raise UnsafeURLError(f"Could not resolve host '{host}'.")
    blocked = [ip for ip in ips if not is_public_ip(ip)]
    if blocked:
        raise UnsafeURLError(
            "That link points to a private or local network address, "
            "which theya.voice refuses to fetch."
        )
