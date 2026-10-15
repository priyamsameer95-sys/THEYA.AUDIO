"""Tier 1: guarded HTTPX fetch + Trafilatura boilerplate removal.

We fetch with HTTPX ourselves (not ``trafilatura.fetch_url``) so we control
the User-Agent, timeouts, body size cap, and SSRF checks on every redirect.
Trafilatura then parses the HTML and returns Markdown, which keeps
code fences and tables intact so the Phase 2 sanitizer can skip them.
"""
from __future__ import annotations

import logging
from typing import Optional, Union
from urllib.parse import urljoin, urlsplit

import httpx
import trafilatura
from trafilatura import extract_metadata

from app import config
from app.extract import guard
from app.extract.models import TIER1_TRAFILATURA, Extraction, FetchError, FetchResult

logger = logging.getLogger("theya.extract.tier1")

BROWSER_HEADERS = {
    "User-Agent": config.USER_AGENT,
    "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


async def fetch_html(
    url: str,
    client: httpx.AsyncClient,
    resolver: Optional[guard.Resolver] = None,
) -> FetchResult:
    """GET ``url``, following redirects manually so each hop is SSRF-checked.

    Non-2xx responses are returned (not raised) so the pipeline can decide
    whether to fall back to Jina. Network errors, oversize bodies and
    non-HTML content raise :class:`FetchError`.
    """
    current = url
    for _ in range(config.MAX_REDIRECTS + 1):
        await guard.check_url(current, resolver)
        request = client.build_request("GET", current, headers=BROWSER_HEADERS)
        try:
            response = await client.send(request, stream=True, follow_redirects=False)
        except httpx.TimeoutException as exc:
            raise FetchError("The website took too long to respond.") from exc
        except httpx.HTTPError as exc:
            raise FetchError(f"Could not reach the website ({type(exc).__name__}).") from exc

        try:
            if response.is_redirect:
                location = response.headers.get("location")
                if not location:
                    raise FetchError("The website sent a redirect without a target.")
                current = urljoin(current, location)
                continue

            content_type = response.headers.get("content-type", "").split(";")[0].strip().lower()
            if response.is_success and content_type and not content_type.startswith(
                config.ALLOWED_CONTENT_TYPES
            ):
                raise FetchError(
                    f"That link is not a webpage (content type '{content_type}')."
                )

            body = await _read_capped(response)
            return FetchResult(
                url=current,
                status=response.status_code,
                body=body,
                content_type=content_type,
            )
        finally:
            await response.aclose()

    raise FetchError(f"Too many redirects (more than {config.MAX_REDIRECTS}).")


async def _read_capped(response: httpx.Response) -> bytes:
    declared = response.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > config.MAX_BODY_BYTES:
        raise FetchError("That page is too large to process.")
    buffer = bytearray()
    try:
        async for chunk in response.aiter_bytes():
            buffer.extend(chunk)
            if len(buffer) > config.MAX_BODY_BYTES:
                raise FetchError("That page is too large to process.")
    except httpx.HTTPError as exc:
        raise FetchError("The connection dropped while downloading the page.") from exc
    return bytes(buffer)


def extract_from_html(
    html: Union[str, bytes],
    url: str,
    tier: str = TIER1_TRAFILATURA,
) -> Optional[Extraction]:
    """Run Trafilatura on raw HTML. Returns ``None`` if nothing was found.

    CPU-bound (lxml parsing), so async callers should wrap this in
    ``asyncio.to_thread`` to keep the event loop responsive.
    """
    if not html:
        return None

    markdown = trafilatura.extract(
        html,
        url=url,
        output_format="markdown",
        include_formatting=True,  # keeps ``` fences, headings, emphasis
        include_tables=True,      # kept so the sanitizer can say "Table skipped"
        include_links=False,
        include_images=False,
        include_comments=False,
        favor_precision=True,     # prefer dropping borderline blocks over nav leaks
        # NOTE: never pass deduplicate=True. Its cache is process-global, so
        # re-extracting the same article (page reload) would return nothing.
    )
    if not markdown or not markdown.strip():
        return None

    meta = extract_metadata(html, default_url=url)
    title = (meta.title if meta else None) or _fallback_title(url)
    return Extraction(
        source_url=url,
        tier=tier,
        title=title.strip(),
        markdown=markdown.strip(),
        byline=meta.author if meta else None,
        sitename=(meta.sitename if meta else None) or urlsplit(url).hostname,
        date=meta.date if meta else None,
    )


def _fallback_title(url: str) -> str:
    return urlsplit(url).hostname or url
