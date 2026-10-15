"""CLI: dump what theya.voice extracts from a URL.

Examples::

    python -m app.extract https://paulgraham.com/greatwork.html
    python -m app.extract https://example.com --no-jina --full
    python -m app.extract https://example.com --html-file saved.html   # Tier 0
    python -m app.extract https://example.com --save-fixture tests/fixtures/live/example.html
    python -m app.extract https://example.com --json
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import warnings
from pathlib import Path

import httpx

from app import config
from app.extract import ExtractionError, extract_article
from app.extract.tier1 import fetch_html

PREVIEW_CHARS = 1500


def _parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="python -m app.extract", description=__doc__.split("\n")[0])
    parser.add_argument("url", help="Article URL to extract")
    parser.add_argument("--html-file", type=Path, help="Use this saved HTML as Tier 0 input")
    parser.add_argument("--no-jina", action="store_true", help="Disable the Tier 2 Jina fallback")
    parser.add_argument("--full", action="store_true", help="Print the full Markdown body")
    parser.add_argument("--json", action="store_true", help="Print the result as JSON")
    parser.add_argument("--save-fixture", type=Path, help="Save the raw fetched HTML to this path")
    parser.add_argument("-v", "--verbose", action="store_true", help="Debug logging")
    return parser.parse_args(argv)


async def _save_fixture(url: str, path: Path) -> None:
    async with httpx.AsyncClient(timeout=config.FETCH_TIMEOUT_S) as client:
        fetched = await fetch_html(url, client)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(fetched.body)
    print(f"Saved {len(fetched.body):,} bytes (HTTP {fetched.status}) → {path}", file=sys.stderr)


async def _main(args: argparse.Namespace) -> int:
    if args.save_fixture:
        await _save_fixture(args.url, args.save_fixture)

    html = args.html_file.read_bytes() if args.html_file else None
    try:
        result = await extract_article(
            args.url, html, jina_enabled=False if args.no_jina else None
        )
    except ExtractionError as exc:
        print(f"✗ {type(exc).__name__}: {exc.message}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
        return 0

    body = result.markdown if args.full else result.markdown[:PREVIEW_CHARS]
    print(f"Title    : {result.title}")
    print(f"Byline   : {result.byline or '-'}   Site: {result.sitename or '-'}   Date: {result.date or '-'}")
    print(f"Tier     : {result.tier}   Words: {result.word_count:,}")
    if result.notes:
        print(f"Fallbacks: {' | '.join(result.notes)}")
    print("-" * 78)
    print(body)
    if not args.full and len(result.markdown) > PREVIEW_CHARS:
        print(f"\n… [{len(result.markdown) - PREVIEW_CHARS:,} more chars, use --full]")
    return 0


def main(argv=None) -> int:
    args = _parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(levelname)-7s %(name)s: %(message)s",
    )
    warnings.filterwarnings("ignore", module="urllib3")  # LibreSSL notice on macOS py3.9
    return asyncio.run(_main(args))


if __name__ == "__main__":
    sys.exit(main())
