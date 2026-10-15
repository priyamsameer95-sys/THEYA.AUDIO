"""Self-healing extraction pipeline: Tier 0 → Tier 1 → Tier 2.

* Tier 0: HTML posted by the bookmarklet (already rendered, logged-in DOM).
* Tier 1: our own guarded fetch + Trafilatura.
* Tier 2: Jina Reader, only when earlier tiers fail the quality gate.

The URL is SSRF-checked *before* any tier runs, so private/LAN URLs are
never fetched locally nor leaked to Jina.
"""
from __future__ import annotations

import asyncio
import logging
from typing import List, Optional, Union

import httpx

from app import config
from app.extract import guard
from app.extract.models import (
    TIER0_HTML,
    Extraction,
    ExtractionError,
    FetchError,
)
from app.extract.quality import assess
from app.extract.tier1 import extract_from_html, fetch_html
from app.extract.tier2 import fetch_via_jina

logger = logging.getLogger("theya.extract")


async def extract_article(
    url: str,
    html: Union[str, bytes, None] = None,
    *,
    client: Optional[httpx.AsyncClient] = None,
    resolver: Optional[guard.Resolver] = None,
    jina_enabled: Optional[bool] = None,
) -> Extraction:
    """Return the best clean extraction for ``url`` or raise ExtractionError."""
    use_jina = config.JINA_ENABLED if jina_enabled is None else jina_enabled
    await guard.check_url(url, resolver)

    owns_client = client is None
    if client is None:
        client = httpx.AsyncClient(timeout=config.FETCH_TIMEOUT_S)

    notes: List[str] = []
    candidates: List[Extraction] = []

    def accept(extraction: Extraction) -> Extraction:
        extraction.notes = notes
        logger.info(
            "Extracted %s via %s (%d words)", url, extraction.tier, extraction.word_count
        )
        return extraction

    try:
        # ---- Tier 0: client-supplied HTML ---------------------------------
        if html:
            t0 = await asyncio.to_thread(extract_from_html, html, url, TIER0_HTML)
            verdict = assess(t0, html)
            if verdict.ok and t0 is not None:
                return accept(t0)
            notes.append(f"tier0: {verdict.summary}")
            if t0 is not None:
                candidates.append(t0)

        # ---- Tier 1: guarded fetch + Trafilatura --------------------------
        # Skipped when Tier 0 HTML was given: the browser's rendered DOM beats
        # a logged-out server refetch. Jina is the better rescue there.
        else:
            t1 = await _run_tier1(url, client, resolver, notes)
            if t1 is not None:
                verdict_ok, t1_extraction = t1
                if verdict_ok:
                    return accept(t1_extraction)
                candidates.append(t1_extraction)

        # ---- Tier 2: Jina Reader -----------------------------------------
        if use_jina:
            try:
                t2 = await fetch_via_jina(url, client)
                verdict = assess(t2)
                if not verdict.ok:
                    notes.append(f"tier2: {verdict.summary}")
                if t2.markdown:
                    candidates.append(t2)
            except FetchError as exc:
                notes.append(f"tier2: {exc.message}")
        else:
            notes.append("tier2: disabled")

        if candidates:
            # Every tier fell short. Keep whichever recovered the most text.
            return accept(max(candidates, key=lambda e: e.word_count))

        raise ExtractionError(
            "Couldn't find a readable article on this page. It may need a login, "
            "block automated readers, or contain no article text. "
            f"Details: {'; '.join(notes) or 'none'}"
        )
    finally:
        if owns_client:
            await client.aclose()


async def _run_tier1(
    url: str,
    client: httpx.AsyncClient,
    resolver: Optional[guard.Resolver],
    notes: List[str],
) -> Optional[tuple]:
    """Return (quality_ok, extraction) or None if Tier 1 produced nothing."""
    try:
        fetched = await fetch_html(url, client, resolver)
    except FetchError as exc:
        # UnsafeURLError (e.g. a redirect to a LAN host) is not a FetchError,
        # so it propagates and aborts the whole pipeline, as intended.
        notes.append(f"tier1: {exc.message}")
        return None

    status = fetched.status
    if status in config.FALLBACK_STATUSES or status >= 500:
        notes.append(f"tier1: HTTP {status}")
        return None
    if status >= 400:
        # 404/410 etc.: the page truly isn't there; Jina won't help.
        raise ExtractionError(f"The website returned HTTP {status} for that link.")

    extraction = await asyncio.to_thread(extract_from_html, fetched.body, fetched.url)
    verdict = assess(extraction, fetched.body)
    if extraction is None:
        notes.append(f"tier1: {verdict.summary}")
        return None
    if not verdict.ok:
        notes.append(f"tier1: {verdict.summary}")
    return verdict.ok, extraction
