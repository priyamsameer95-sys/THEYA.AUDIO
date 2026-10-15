"""In-memory byte-budgeted LRU audio cache with in-flight deduplication."""
from __future__ import annotations

import asyncio
from collections import OrderedDict
import hashlib
import logging
from typing import Dict, Optional, Tuple

from app import config

logger = logging.getLogger("theya.tts.cache")


class AudioLRUCache:
    """Thread/asyncio-safe LRU cache storing synthesized audio bytes in RAM.

    Bounded by both item count and total byte budget (default 256 MB).
    Provides in-flight deduplication so concurrent requests for the same sentence
    (e.g. prefetch + active playback) execute synthesis only once.
    """

    def __init__(
        self,
        max_items: int = config.AUDIO_CACHE_MAX_ITEMS,
        max_bytes: int = config.AUDIO_CACHE_MAX_BYTES,
    ) -> None:
        self.max_items = max_items
        self.max_bytes = max_bytes
        self._store: OrderedDict[str, bytes] = OrderedDict()
        self._current_bytes: int = 0
        self._inflight: Dict[str, asyncio.Future[bytes]] = {}
        self._lock: Optional[asyncio.Lock] = None

    def _get_lock(self) -> asyncio.Lock:
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    @staticmethod
    def make_key(text: str, voice: str, rate: str, engine: str = "edge") -> str:
        raw = f"{engine}|{voice}|{rate}|{text.strip()}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    @property
    def current_bytes(self) -> int:
        return self._current_bytes

    @property
    def item_count(self) -> int:
        return len(self._store)

    def get(self, key: str) -> Optional[bytes]:
        """Returns cached audio bytes and moves key to the most-recently-used end."""
        if key not in self._store:
            return None
        self._store.move_to_end(key)
        return self._store[key]

    def put(self, key: str, audio_bytes: bytes) -> None:
        """Stores audio bytes and evicts oldest items if over budget."""
        if key in self._store:
            self._current_bytes -= len(self._store[key])
            self._store.move_to_end(key)
        self._store[key] = audio_bytes
        self._current_bytes += len(audio_bytes)

        # Evict by item count
        while len(self._store) > self.max_items:
            _, evicted = self._store.popitem(last=False)
            self._current_bytes -= len(evicted)

        # Evict by byte budget
        while self._current_bytes > self.max_bytes and self._store:
            _, evicted = self._store.popitem(last=False)
            self._current_bytes -= len(evicted)

    async def get_or_synthesize(
        self,
        key: str,
        synthesize_fn,
    ) -> Tuple[bytes, bool]:
        """Gets cached audio or calls synthesize_fn with in-flight deduplication.

        Returns (audio_bytes, was_cache_hit).
        """
        # Fast path: check memory cache
        cached = self.get(key)
        if cached is not None:
            return cached, True

        # Check in-flight
        future: Optional[asyncio.Future[bytes]] = None
        is_leader = False

        async with self._get_lock():
            # Recheck cache inside lock
            cached = self.get(key)
            if cached is not None:
                return cached, True

            if key in self._inflight:
                future = self._inflight[key]
            else:
                loop = asyncio.get_running_loop()
                future = loop.create_future()
                self._inflight[key] = future
                is_leader = True

        if not is_leader:
            # Follower: await the leader's future
            assert future is not None
            audio_bytes = await future
            return audio_bytes, True

        # Leader: perform synthesis
        try:
            audio_bytes = await synthesize_fn()
            self.put(key, audio_bytes)
            future.set_result(audio_bytes)
            return audio_bytes, False
        except BaseException as exc:
            if not future.done():
                future.set_exception(exc)
            raise
        finally:
            async with self._get_lock():
                self._inflight.pop(key, None)

    def clear(self) -> None:
        self._store.clear()
        self._current_bytes = 0


# Global singleton cache instance
AUDIO_CACHE = AudioLRUCache()
