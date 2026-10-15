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
