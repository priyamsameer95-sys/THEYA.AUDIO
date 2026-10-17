"""Unit tests for Phase 3: Audio LRU Cache and in-flight deduplication."""
from __future__ import annotations

import asyncio
import pytest

from app.tts.cache import AudioLRUCache


def test_cache_put_get() -> None:
    cache = AudioLRUCache(max_items=3, max_bytes=1000)
    cache.put("k1", b"audio1")
    assert cache.get("k1") == b"audio1"
    assert cache.get("nonexistent") is None


def test_cache_eviction_by_item_count() -> None:
    cache = AudioLRUCache(max_items=2, max_bytes=1000)
    cache.put("k1", b"audio1")
    cache.put("k2", b"audio2")
    cache.put("k3", b"audio3")  # should evict k1

    assert cache.get("k1") is None
    assert cache.get("k2") == b"audio2"
    assert cache.get("k3") == b"audio3"


def test_cache_eviction_by_byte_budget() -> None:
    # 20 bytes max
    cache = AudioLRUCache(max_items=10, max_bytes=20)
    cache.put("k1", b"1234567890")  # 10 bytes
    cache.put("k2", b"1234567890")  # 10 bytes -> total 20 bytes
    assert cache.current_bytes == 20

    cache.put("k3", b"1234567890")  # another 10 bytes -> evicts k1
    assert cache.get("k1") is None
    assert cache.get("k2") == b"1234567890"
    assert cache.get("k3") == b"1234567890"
    assert cache.current_bytes == 20


def test_cache_inflight_deduplication() -> None:
    """When multiple concurrent calls ask for the same key, synthesize_fn runs only once."""
    from tests.conftest import run

    async def _test():
        cache = AudioLRUCache()
        call_count = 0

        async def fake_synth():
            nonlocal call_count
            call_count += 1
            await asyncio.sleep(0.05)
            return b"synthesized_audio"

        # Launch 5 concurrent calls for the same key
        results = await asyncio.gather(
            cache.get_or_synthesize("same_key", fake_synth),
            cache.get_or_synthesize("same_key", fake_synth),
            cache.get_or_synthesize("same_key", fake_synth),
            cache.get_or_synthesize("same_key", fake_synth),
            cache.get_or_synthesize("same_key", fake_synth),
        )

        # All 5 return the same audio bytes
        for audio_bytes, _ in results:
            assert audio_bytes == b"synthesized_audio"

        # But fake_synth was called exactly once!
        assert call_count == 1
        # Cache now contains the item
        assert cache.get("same_key") == b"synthesized_audio"

    run(_test())


def test_kokoro_inference_client_fal_ai(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verifies Kokoro-82M calls huggingface_hub.InferenceClient(provider='fal-ai') with model='hexgrad/Kokoro-82M'."""
    from app.tts import kokoro

    recorded_init = {}
    recorded_call = {}

    class DummyInferenceClient:
        def __init__(self, provider: str = "", api_key: str = "") -> None:
            recorded_init["provider"] = provider
            recorded_init["api_key"] = api_key

        def text_to_speech(self, text: str, model: str = "") -> bytes:
            recorded_call["text"] = text
            recorded_call["model"] = model
            return b"RIFF_fake_kokoro_audio_bytes"

    monkeypatch.setattr(kokoro, "InferenceClient", DummyInferenceClient)
    monkeypatch.setenv("HF_TOKEN", "hf_test_secret_token")

    audio = kokoro.synthesize_kokoro_sync("The answer to the universe is 42")
    assert audio == b"RIFF_fake_kokoro_audio_bytes"
    assert recorded_init["provider"] == "fal-ai"
    assert recorded_init["api_key"] == "hf_test_secret_token"
    assert recorded_call["text"] == "The answer to the universe is 42"
    assert recorded_call["model"] == "hexgrad/Kokoro-82M"


def test_hf_token_api_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verifies /api/settings/hf-token sets HF_TOKEN for Kokoro-82M."""
    import os
    from fastapi.testclient import TestClient
    from app.main import app

    monkeypatch.delenv("HF_TOKEN", raising=False)
    client = TestClient(app)

    res_post = client.post("/api/settings/hf-token", json={"token": "hf_demo_1234567890"})
    assert res_post.status_code == 200
    assert res_post.json()["configured"] is True
    assert res_post.json()["model"] == "hexgrad/Kokoro-82M"
    assert res_post.json()["provider"] == "fal-ai"
    assert os.environ.get("HF_TOKEN") == "hf_demo_1234567890"

    res_get = client.get("/api/settings/hf-token")
    assert res_get.status_code == 200
    assert res_get.json()["configured"] is True
    assert "hf_de...7890" in (res_get.json()["masked_token"] or "")
    monkeypatch.delenv("HF_TOKEN", raising=False)

