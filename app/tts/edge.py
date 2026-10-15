"""Edge-TTS integration for studio-quality Microsoft Neural speech."""
from __future__ import annotations

import logging
import edge_tts

logger = logging.getLogger("theya.tts.edge")


async def synthesize_edge_tts(text: str, voice: str, rate: str = "+0%") -> bytes:
    """Synthesizes text into MP3 audio bytes using edge-tts.

    Raises RuntimeError on empty or failed audio stream.
    """
    clean_text = text.strip()
    if not clean_text:
        raise ValueError("Cannot synthesize empty text.")

    communicate = edge_tts.Communicate(text=clean_text, voice=voice, rate=rate)

    # If text contains SSML break markers, restore unescaped tags in Communicate texts
    if "<break" in clean_text:
        import re
        unescaped_chunks = []
        for chunk in communicate.texts:
            decoded = chunk.decode("utf-8") if isinstance(chunk, bytes) else chunk
            fixed = re.sub(r'&lt;break\s+time="([^"]+)"\s*/?&gt;', r'<break time="\1"/>', decoded)
            unescaped_chunks.append(fixed.encode("utf-8"))
        communicate.texts = iter(unescaped_chunks)

    audio_buffer = bytearray()
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            audio_buffer.extend(chunk["data"])

    if not audio_buffer:
        raise RuntimeError("Edge-TTS returned an empty audio stream.")

    return bytes(audio_buffer)
