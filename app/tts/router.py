"""TTS router managing synthesis, caching, and engine selection."""
from __future__ import annotations

import logging
from typing import Tuple

from app.tts.cache import AUDIO_CACHE, AudioLRUCache
from app.tts.edge import synthesize_edge_tts
from app.tts.kokoro import synthesize_kokoro_tts
from app.tts.voices import DEFAULT_VOICE_ID

logger = logging.getLogger("theya.tts.router")


async def get_or_synthesize_speech(
    text: str,
    voice: str = DEFAULT_VOICE_ID,
    rate: str = "+0%",
    engine: str = "edge",
) -> Tuple[bytes, bool]:
    """Retrieves audio from cache or synthesizes it.

    Returns:
        (audio_bytes, was_cache_hit)
    """
    effective_engine = "kokoro" if (engine == "kokoro" or voice.startswith("kokoro:")) else engine
    key = AudioLRUCache.make_key(text=text, voice=voice, rate=rate, engine=effective_engine)

    async def _do_synth() -> bytes:
        if effective_engine == "kokoro":
            return await synthesize_kokoro_tts(text=text, voice=voice, rate=rate)
        if effective_engine == "edge":
            return await synthesize_edge_tts(text=text, voice=voice, rate=rate)
        raise ValueError(f"Unknown TTS engine: {engine}")

    return await AUDIO_CACHE.get_or_synthesize(key, _do_synth)
