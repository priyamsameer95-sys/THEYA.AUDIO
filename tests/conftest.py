"""Shared test helpers: fixtures on disk, fake DNS, and a mock HTTP world."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Callable, Dict, List

import httpx
import pytest

FIXTURES = Path(__file__).parent / "fixtures"

PUBLIC_IP = "93.184.216.34"

# Hostname -> IPs. Anything missing resolves to nothing (→ UnsafeURLError).
FAKE_DNS: Dict[str, List[str]] = {
    "blog.example": [PUBLIC_IP],
    "spa.example": [PUBLIC_IP],
    "blocked.example": [PUBLIC_IP],
    "gone.example": [PUBLIC_IP],
    "huge.example": [PUBLIC_IP],
    "loop.example": [PUBLIC_IP],
    "redirect.example": [PUBLIC_IP],
    "localhost": ["127.0.0.1"],
    "lan.example": ["192.168.1.10"],
    "metadata.example": ["169.254.169.254"],
    "mixed.example": [PUBLIC_IP, "10.0.0.5"],
    "mapped.example": ["::ffff:127.0.0.1"],
}


async def fake_resolver(host: str, port: int) -> List[str]:
    return FAKE_DNS.get(host, [])


def read_fixture(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def run(coro):
    """Run a coroutine without needing pytest-asyncio."""
    return asyncio.run(coro)


class MockWeb:
    """Routes requests to canned responses and records every URL hit."""

    def __init__(self) -> None:
        self.calls: List[str] = []
        self.jina_status = 200

    @property
    def jina_calls(self) -> List[str]:
        return [c for c in self.calls if c.startswith("https://r.jina.ai/")]

    def handler(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        self.calls.append(url)
        host = request.url.host
        html_headers = {"content-type": "text/html; charset=utf-8"}

        if host == "r.jina.ai":
            if self.jina_status != 200:
                return httpx.Response(self.jina_status, json={"message": "nope"})
            return httpx.Response(200, json=json.loads(read_fixture("jina_spa_response.json")))
        if host == "blog.example":
            return httpx.Response(200, headers=html_headers, content=read_fixture("blog_with_chrome.html"))
        if host == "spa.example":
            return httpx.Response(200, headers=html_headers, content=read_fixture("spa_shell.html"))
        if host == "blocked.example":
            return httpx.Response(403, headers=html_headers, content=b"<h1>Access denied</h1>")
        if host == "gone.example":
            return httpx.Response(404, headers=html_headers, content=b"<h1>Not found</h1>")
        if host == "huge.example":
            return httpx.Response(200, headers=html_headers, content=b"<p>x</p>" * 2000)
        if host == "loop.example":
            return httpx.Response(302, headers={"location": "/again"})
        if host == "redirect.example":
            target = request.url.params.get("to", "https://blog.example/post")
            return httpx.Response(301, headers={"location": target})
        if host == "pdf.example":
            return httpx.Response(200, headers={"content-type": "application/pdf"}, content=b"%PDF")
        return httpx.Response(599, content=b"unexpected host in test")

    def client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.MockTransport(self.handler))


@pytest.fixture
def web() -> MockWeb:
    return MockWeb()


@pytest.fixture
def make_client(web: MockWeb) -> Callable[[], httpx.AsyncClient]:
    return web.client
