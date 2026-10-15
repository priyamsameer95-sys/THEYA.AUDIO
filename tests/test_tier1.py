"""Tier 1 Trafilatura extraction + quality gate tests (pure, no network)."""
from __future__ import annotations

import pytest

from app.extract.models import Extraction
from app.extract.quality import assess, looks_like_spa_shell
from app.extract.tier1 import extract_from_html
from tests.conftest import read_fixture

BLOG_URL = "https://blog.example/post"

# Strings that live only in the site chrome. None may leak into the article.
CHROME_STRINGS = [
    "Accept all cookies",
    "Manage preferences",
    "Sitemap",
    "Pricing",
    "About Us",
    "Sign In",
    "Search TechBlog",
    "Trending Posts",
    "Top 10 VS Code Themes",
    "Subscribe",
    "All rights reserved",
    "Terms",
]


@pytest.fixture(scope="module")
def blog() -> Extraction:
    result = extract_from_html(read_fixture("blog_with_chrome.html"), BLOG_URL)
    assert result is not None
    return result


def test_blog_metadata(blog: Extraction) -> None:
    assert blog.title == "Why Async Python Scales So Well"
    assert blog.byline == "Jane Doe"
    assert blog.tier == "tier1-trafilatura"


def test_blog_keeps_article_prose(blog: Extraction) -> None:
    assert "Traditional synchronous web servers block" in blog.markdown
    assert "concurrency is about structure" in blog.markdown
    assert "## A tiny example" in blog.markdown


@pytest.mark.parametrize("chrome", CHROME_STRINGS)
def test_blog_strips_site_chrome(blog: Extraction, chrome: str) -> None:
    assert chrome not in blog.markdown


def test_blog_keeps_code_fences_for_sanitizer(blog: Extraction) -> None:
    """Regression for guide bug B1: code must stay fenced so Phase 2 can skip it."""
    assert "```" in blog.markdown
    assert "asyncio.gather" in blog.markdown


def test_blog_keeps_tables_for_sanitizer(blog: Extraction) -> None:
    assert "| Server model | Requests per second |" in blog.markdown


def test_blog_passes_quality_gate(blog: Extraction) -> None:
    verdict = assess(blog, read_fixture("blog_with_chrome.html"))
    assert verdict.ok, verdict.summary


def test_spa_shell_is_detected() -> None:
    html = read_fixture("spa_shell.html")
    assert looks_like_spa_shell(html)
    verdict = assess(extract_from_html(html, "https://spa.example/posts/realtime"), html)
    assert not verdict.ok


def test_long_article_with_noscript_notice_is_trusted(blog: Extraction) -> None:
    """A 'please enable JavaScript' banner alone must not discard a good article."""
    html = read_fixture("blog_with_chrome.html") + b"<noscript>Please enable JavaScript</noscript>"
    padded = Extraction(
        source_url=BLOG_URL, tier=blog.tier, title=blog.title,
        markdown=blog.markdown + (" filler words" * 150),
    )
    assert assess(padded, html).ok


def test_empty_html_returns_none() -> None:
    assert extract_from_html(b"", BLOG_URL) is None
    assert extract_from_html("<html><body></body></html>", BLOG_URL) is None
