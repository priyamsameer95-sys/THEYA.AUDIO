"""Live smoke tests against real websites. Skipped unless THEYA_LIVE=1.

    THEYA_LIVE=1 .venv/bin/pytest -m live -v
"""
from __future__ import annotations

import os

import pytest

from app.extract import extract_article
from tests.conftest import run

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(os.getenv("THEYA_LIVE") != "1", reason="set THEYA_LIVE=1 to hit the network"),
]

NAV_JUNK = ["Sign in", "Log in", "Cookie", "Sitemap", "Privacy Policy"]


@pytest.mark.parametrize(
    "url, must_contain",
    [
        ("https://paulgraham.com/greatwork.html", "great work"),
        ("https://en.wikipedia.org/wiki/Speech_synthesis", "speech"),
        ("https://docs.python.org/3/library/asyncio-task.html", "coroutine"),
    ],
)
def test_live_extraction_is_clean(url: str, must_contain: str) -> None:
    result = run(extract_article(url))
    assert result.word_count > 300
    assert must_contain.lower() in result.markdown.lower()
    head = result.markdown[:400]
    for junk in NAV_JUNK:
        assert junk not in head, f"nav junk '{junk}' at start of {url}"
