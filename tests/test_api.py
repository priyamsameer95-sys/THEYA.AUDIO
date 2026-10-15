"""Integration tests for FastAPI endpoints."""
from __future__ import annotations

import httpx
import pytest

from app.main import app
from tests.conftest import run


def test_serve_index() -> None:
    async def _test():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/")
            assert resp.status_code == 200
            assert "theya.voice" in resp.text
            assert "text/html" in resp.headers["content-type"]

    run(_test())


def test_get_voices() -> None:
    async def _test():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/api/voices")
            assert resp.status_code == 200
            data = resp.json()
            assert "voices" in data
            assert len(data["voices"]) > 0
            assert any("Andrew" in v["label"] for v in data["voices"])

    run(_test())


def test_extract_invalid_url_rejected() -> None:
    async def _test():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post("/api/extract", json={"url": "not-a-valid-url"})
            assert resp.status_code == 422  # Pydantic validation error

    run(_test())


def test_extract_ssrf_blocked() -> None:
    async def _test():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post("/api/extract", json={"url": "http://127.0.0.1:8000/"})
            assert resp.status_code == 400
            assert "refuses to fetch" in resp.json()["detail"]

    run(_test())


def test_tts_endpoint_with_cache() -> None:
    from app.tts.cache import AUDIO_CACHE

    # Pre-seed cache to avoid relying on external Microsoft Edge endpoint during tests
    key = AUDIO_CACHE.make_key(text="Test audio", voice="en-US-AndrewMultilingualNeural", rate="+0%", engine="edge")
    AUDIO_CACHE.put(key, b"FAKE_MP3_DATA_123")

    async def _test():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get(
                "/api/tts",
                params={"text": "Test audio", "voice": "en-US-AndrewMultilingualNeural"},
            )
            assert resp.status_code == 200
            assert resp.headers["content-type"] == "audio/mpeg"
            assert resp.headers["x-cache"] == "HIT"
            assert resp.content == b"FAKE_MP3_DATA_123"

    run(_test())


def test_multilingual_voices_grouped() -> None:
    async def _test():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/api/voices")
            assert resp.status_code == 200
            voices = resp.json()["voices"]
            languages = {v.get("language") for v in voices}
            assert "Spanish" in languages
            assert "French" in languages
            assert "German" in languages
            assert "Hindi" in languages
            assert "Japanese" in languages
            assert "Chinese" in languages

    run(_test())


def test_feedback_submit_and_retrieve() -> None:
    async def _test():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            # Submit feedback
            post_resp = await client.post(
                "/api/feedback",
                json={
                    "rating": 5,
                    "feedback_type": "general",
                    "article_url": "https://example.com/great-article",
                    "sentence_idx": 3,
                    "comments": "Super clean audio output!",
                },
            )
            assert post_resp.status_code == 200
            assert post_resp.json()["status"] == "ok"

            # Retrieve feedback
            get_resp = await client.get("/api/feedback?limit=10")
            assert get_resp.status_code == 200
            feedback_list = get_resp.json()["feedback"]
            assert len(feedback_list) > 0
            latest = feedback_list[-1]
            assert latest["rating"] == 5
            assert latest["comments"] == "Super clean audio output!"

    run(_test())


def test_progress_and_history_endpoints() -> None:
    async def _test():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            # 1. Update progress for a URL
            prog_resp = await client.post(
                "/api/progress",
                json={
                    "url": "https://example.com/history-test-article",
                    "current_sentence_idx": 5,
                    "total_sentences": 10,
                },
            )
            assert prog_resp.status_code == 200
            data = prog_resp.json()
            assert data["status"] == "ok"
            assert data["progress"]["current_sentence_idx"] == 5
            assert data["progress"]["total_sentences"] == 10
            assert data["progress"]["completion_ratio"] == 0.5
            assert data["progress"]["is_completed"] is False

            # 2. Complete reading
            prog_resp2 = await client.post(
                "/api/progress",
                json={
                    "url": "https://example.com/history-test-article",
                    "current_sentence_idx": 9,
                    "total_sentences": 10,
                },
            )
            assert prog_resp2.status_code == 200
            assert prog_resp2.json()["progress"]["is_completed"] is True

            # 3. Retrieve history
            hist_resp = await client.get("/api/history?limit=10")
            assert hist_resp.status_code == 200
            history = hist_resp.json()["history"]
            assert len(history) > 0
            match = next((item for item in history if item["url"] == "https://example.com/history-test-article"), None)
            assert match is not None
            assert match["is_completed"] == 1

    run(_test())

