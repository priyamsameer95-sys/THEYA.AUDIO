"""Tier 2: Jina Reader (https://r.jina.ai/) fallback for JS-rendered pages.

Jina renders the page in a cloud headless browser and returns Markdown, so
we get SPA support without installing Chromium locally.

Trade-offs (shown to the user via ``Extraction.tier``):
* Free without a key, but rate-limited (~20 requests/min per IP).
* The target URL is sent to a third party. Disable with THEYA_JINA_ENABLED=0.
"""
from __future__ import annotations

import logging
from urllib.parse import urlsplit

import httpx

from app import config
from app.extract.models import TIER2_JINA, Extraction, FetchError

logger = logging.getLogger("theya.extract.tier2")


def _jina_headers() -> dict:
    headers = {
        "Accept": "application/json",
        "X-Return-Format": "markdown",
        "X-Retain-Images": "none",
        "X-Remove-Selector": config.JINA_REMOVE_SELECTORS,
        "User-Agent": "theya.voice/0.1 (+local reader)",
    }
    if config.JINA_API_KEY:
        headers["Authorization"] = f"Bearer {config.JINA_API_KEY}"
    return headers


async def fetch_via_jina(url: str, client: httpx.AsyncClient) -> Extraction:
    """Ask Jina Reader to render ``url``. Raises :class:`FetchError` on failure."""
    endpoint = f"{config.JINA_BASE_URL}{url}"
    try:
        response = await client.get(
            endpoint,
            headers=_jina_headers(),
            timeout=config.JINA_TIMEOUT_S,
            follow_redirects=True,
        )
    except httpx.TimeoutException as exc:
        raise FetchError("The JavaScript renderer (Jina Reader) timed out.") from exc
    except httpx.HTTPError as exc:
        raise FetchError(f"Could not reach Jina Reader ({type(exc).__name__}).") from exc

    if response.status_code == 429:
        raise FetchError("Jina Reader rate limit hit. Wait a minute and try again.")
    if not response.is_success:
        raise FetchError(f"Jina Reader failed with HTTP {response.status_code}.")

    try:
        data = response.json().get("data") or {}
        content = data.get("content") or ""
        title = data.get("title") or ""
        published = data.get("publishedTime")
    except ValueError:
        # Plain-text/Markdown reply (e.g. if the Accept header was ignored).
        content, title, published = response.text, "", None

    host = urlsplit(url).hostname or url
    return Extraction(
        source_url=url,
        tier=TIER2_JINA,
        title=(title or host).strip(),
        markdown=content.strip(),
        sitename=host,
        date=published,
    )
