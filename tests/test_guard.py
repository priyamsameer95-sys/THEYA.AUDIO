"""SSRF guard tests: only public http(s) hosts may be fetched."""
from __future__ import annotations

import pytest

from app.extract.guard import check_url, is_public_ip, validate_url_syntax
from app.extract.models import UnsafeURLError
from tests.conftest import fake_resolver, run


@pytest.mark.parametrize(
    "ip, expected",
    [
        ("93.184.216.34", True),
        ("2606:2800:220:1:248:1893:25c8:1946", True),
        ("127.0.0.1", False),
        ("10.1.2.3", False),
        ("172.16.0.1", False),
        ("192.168.0.10", False),
        ("169.254.169.254", False),  # cloud metadata
        ("100.64.0.1", False),       # carrier-grade NAT
        ("0.0.0.0", False),
        ("::1", False),
        ("fe80::1%en0", False),      # link-local with zone id
        ("fc00::1", False),          # unique local
        ("::ffff:127.0.0.1", False), # IPv4-mapped loopback
        ("224.0.0.1", False),        # multicast
    ],
)
def test_is_public_ip(ip: str, expected: bool) -> None:
    assert is_public_ip(ip) is expected


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "ftp://example.com/file",
        "javascript:alert(1)",
        "http://",
        "not a url",
        "http://user:secret@example.com/",
        "http://example.com:99999/",
    ],
)
def test_validate_url_syntax_rejects(url: str) -> None:
    with pytest.raises(UnsafeURLError):
        validate_url_syntax(url)


def test_validate_url_syntax_defaults_ports() -> None:
    assert validate_url_syntax("https://Blog.Example/post") == ("https", "blog.example", 443)
    assert validate_url_syntax("http://blog.example:8080/") == ("http", "blog.example", 8080)


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost:8000/",
        "http://lan.example/router",
        "http://metadata.example/latest/meta-data/",
        "http://mixed.example/",   # one private IP is enough to block
        "http://mapped.example/",
        "http://unknown.example/", # does not resolve
    ],
)
def test_check_url_blocks_private_and_unresolvable(url: str) -> None:
    with pytest.raises(UnsafeURLError):
        run(check_url(url, fake_resolver))


def test_check_url_allows_public() -> None:
    run(check_url("https://blog.example/post", fake_resolver))  # no exception
