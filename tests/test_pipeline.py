"""End-to-end pipeline tests against a mocked web (no real network)."""
from __future__ import annotations

import pytest

from app import config
from app.extract import ExtractionError, UnsafeURLError, extract_article
from tests.conftest import fake_resolver, read_fixture, run


def _extract(web, url, **kwargs):
    async def go():
        async with web.client() as client:
            return await extract_article(url, client=client, resolver=fake_resolver, **kwargs)

    return run(go())


def test_static_blog_uses_tier1_and_never_calls_jina(web) -> None:
    result = _extract(web, "https://blog.example/post")
    assert result.tier == "tier1-trafilatura"
    assert result.title == "Why Async Python Scales So Well"
    assert web.jina_calls == []
    assert result.notes == []


def test_spa_shell_falls_back_to_jina(web) -> None:
    result = _extract(web, "https://spa.example/posts/realtime")
    assert result.tier == "tier2-jina"
    assert result.title == "Building Realtime Dashboards"
    assert "server-sent events" in result.markdown
    assert web.jina_calls == ["https://r.jina.ai/https://spa.example/posts/realtime"]
    assert any(n.startswith("tier1:") for n in result.notes)


def test_bot_wall_403_falls_back_to_jina(web) -> None:
    result = _extract(web, "https://blocked.example/article")
    assert result.tier == "tier2-jina"
    assert "tier1: HTTP 403" in result.notes


def test_404_is_a_hard_error_without_jina(web) -> None:
    with pytest.raises(ExtractionError, match="HTTP 404"):
        _extract(web, "https://gone.example/missing")
    assert web.jina_calls == []


def test_private_url_is_rejected_before_any_request(web) -> None:
    with pytest.raises(UnsafeURLError):
        _extract(web, "http://lan.example/admin")
    assert web.calls == []  # nothing fetched locally, nothing leaked to Jina


def test_redirect_into_private_network_is_blocked(web) -> None:
    with pytest.raises(UnsafeURLError):
        _extract(web, "https://redirect.example/?to=http://lan.example/admin")
    assert web.jina_calls == []
    assert not any(c.startswith("http://lan.example") for c in web.calls)


def test_reextracting_same_article_still_works(web) -> None:
    """Regression: Trafilatura's global dedup cache must stay off."""
    first = _extract(web, "https://blog.example/post")
    second = _extract(web, "https://blog.example/post")
    assert first.tier == second.tier == "tier1-trafilatura"
    assert second.word_count == first.word_count


def test_safe_redirect_is_followed(web) -> None:
    result = _extract(web, "https://redirect.example/?to=https://blog.example/post")
    assert result.tier == "tier1-trafilatura"


def test_redirect_loop_falls_back_to_jina(web) -> None:
    result = _extract(web, "https://loop.example/start")
    assert result.tier == "tier2-jina"
    assert any("Too many redirects" in n for n in result.notes)


def test_oversized_page_is_capped(web, monkeypatch) -> None:
    monkeypatch.setattr(config, "MAX_BODY_BYTES", 1024)
    result = _extract(web, "https://huge.example/big")
    assert result.tier == "tier2-jina"
    assert any("too large" in n for n in result.notes)


def test_non_html_content_type_is_rejected(web, monkeypatch) -> None:
    from tests import conftest

    monkeypatch.setitem(conftest.FAKE_DNS, "pdf.example", [conftest.PUBLIC_IP])
    with pytest.raises(ExtractionError) as exc_info:
        _extract(web, "https://pdf.example/paper.pdf", jina_enabled=False)
    assert "not a webpage" in exc_info.value.message


def test_spa_with_jina_disabled_reports_clear_error(web) -> None:
    with pytest.raises(ExtractionError) as exc_info:
        _extract(web, "https://spa.example/posts/realtime", jina_enabled=False)
    assert "tier2: disabled" in exc_info.value.message
    assert web.jina_calls == []


def test_jina_rate_limit_is_reported(web) -> None:
    web.jina_status = 429
    with pytest.raises(ExtractionError) as exc_info:
        _extract(web, "https://spa.example/posts/realtime")
    assert "rate limit" in exc_info.value.message


def test_tier0_html_skips_all_network(web) -> None:
    result = _extract(web, "https://blog.example/post", html=read_fixture("blog_with_chrome.html"))
    assert result.tier == "tier0-client-html"
    assert web.calls == []
