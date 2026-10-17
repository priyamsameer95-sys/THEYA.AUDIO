"""Edge-TTS integration for studio-quality Microsoft Neural speech."""
from __future__ import annotations

import logging
import re
import edge_tts

logger = logging.getLogger("theya.tts.edge")


async def synthesize_edge_tts(text: str, voice: str, rate: str = "+0%") -> bytes:
    """Synthesizes text into MP3 audio bytes using edge-tts.

    Raises RuntimeError on empty or failed audio stream.
    """
    clean_text = text.strip()
    if "<break" in clean_text:
        clean_text = re.sub(r"^(?:<break\b[^>]*/?>\s*)+", "", clean_text, flags=re.IGNORECASE)
        clean_text = re.sub(r"(?:\s*<break\b[^>]*/?>)+$", "", clean_text, flags=re.IGNORECASE)
        clean_text = re.sub(
            r"([—–:,.;?!])\s*<break\b[^>]*/?>\s*", r"\1 ", clean_text, flags=re.IGNORECASE
        )
        clean_text = re.sub(r"\s*<break\b[^>]*/?>\s*", " ... ", clean_text, flags=re.IGNORECASE)
    # Strip any stray markdown table pipes so TTS never chokes or reads pipes
    clean_text = re.sub(r"(?:\|\s*)+", " ", clean_text)
    clean_text = re.sub(r"\s{2,}", " ", clean_text).strip()

    if not clean_text:
        raise ValueError("Cannot synthesize empty text.")

    communicate = edge_tts.Communicate(text=clean_text, voice=voice, rate=rate)

    audio_buffer = bytearray()
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            audio_buffer.extend(chunk["data"])

    if not audio_buffer:
        raise RuntimeError("Edge-TTS returned an empty audio stream.")

    return bytes(audio_buffer)
