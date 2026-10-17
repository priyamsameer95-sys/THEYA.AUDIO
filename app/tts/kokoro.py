"""Kokoro-82M integration via Hugging Face InferenceClient (fal-ai provider).

Model: https://huggingface.co/hexgrad/Kokoro-82M
GitHub: https://github.com/hexgrad/kokoro
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
from typing import Dict, List, Optional

from huggingface_hub import InferenceClient, get_token

logger = logging.getLogger("theya.tts.kokoro")

KOKORO_MODEL_ID = "hexgrad/Kokoro-82M"
KOKORO_PROVIDER = "fal-ai"

KOKORO_VOICES: List[Dict[str, str]] = [
    {
        "id": "kokoro:af_heart",
        "label": "Kokoro · Heart (US Female - Studio Flagship)",
        "gender": "Female",
        "locale": "en-US",
        "language": "English (Kokoro-82M)",
    },
    {
        "id": "kokoro:am_adam",
        "label": "Kokoro · Adam (US Male - Deep & Warm)",
        "gender": "Male",
        "locale": "en-US",
        "language": "English (Kokoro-82M)",
    },
    {
        "id": "kokoro:af_bella",
        "label": "Kokoro · Bella (US Female - Expressive)",
        "gender": "Female",
        "locale": "en-US",
        "language": "English (Kokoro-82M)",
    },
    {
        "id": "kokoro:am_michael",
        "label": "Kokoro · Michael (US Male - Conversational)",
        "gender": "Male",
        "locale": "en-US",
        "language": "English (Kokoro-82M)",
    },
    {
        "id": "kokoro:bf_emma",
        "label": "Kokoro · Emma (UK Female - Editorial)",
        "gender": "Female",
        "locale": "en-GB",
        "language": "English (Kokoro-82M)",
    },
    {
        "id": "kokoro:bm_george",
        "label": "Kokoro · George (UK Male - Monograph)",
        "gender": "Male",
        "locale": "en-GB",
        "language": "English (Kokoro-82M)",
    },
]


def resolve_hf_token() -> Optional[str]:
    """Resolves HF_TOKEN from environment or local Hugging Face cache."""
    env_token = (
        os.environ.get("HF_TOKEN", "").strip()
        or os.environ.get("HUGGINGFACE_HUB_TOKEN", "").strip()
        or os.environ.get("HF_API_TOKEN", "").strip()
    )
    if env_token:
        return env_token
    cached = get_token()
    return cached.strip() if cached else None


def set_hf_token(token: str) -> bool:
    """Sets HF_TOKEN in process environment for immediate Kokoro-82M synthesis."""
    cleaned = token.strip()
    if not cleaned:
        os.environ.pop("HF_TOKEN", None)
        return False
    os.environ["HF_TOKEN"] = cleaned
    return True


def _clean_text_for_kokoro(text: str) -> str:
    """Strips SSML tags and stray markdown pipes before sending to Kokoro-82M."""
    clean_text = text.strip()
    if "<break" in clean_text:
        clean_text = re.sub(r"^(?:<break\b[^>]*/?>\s*)+", "", clean_text, flags=re.IGNORECASE)
        clean_text = re.sub(r"(?:\s*<break\b[^>]*/?>)+$", "", clean_text, flags=re.IGNORECASE)
        clean_text = re.sub(
            r"([—–:,.;?!])\s*<break\b[^>]*/?>\s*", r"\1 ", clean_text, flags=re.IGNORECASE
        )
        clean_text = re.sub(r"\s*<break\b[^>]*/?>\s*", " ... ", clean_text, flags=re.IGNORECASE)
    clean_text = re.sub(r"(?:\|\s*)+", " ", clean_text)
    clean_text = re.sub(r"\s{2,}", " ", clean_text).strip()
    return clean_text


def synthesize_kokoro_sync(text: str, api_key: Optional[str] = None) -> bytes:
    """Synchronous Kokoro-82M TTS call using huggingface_hub.InferenceClient (fal-ai)."""
    clean_text = _clean_text_for_kokoro(text)
    if not clean_text:
        raise ValueError("Cannot synthesize empty text with Kokoro-82M.")

    token = api_key or os.environ.get("HF_TOKEN") or resolve_hf_token()
    if not token:
        raise RuntimeError(
            "HF_TOKEN is not set. Please set HF_TOKEN in your environment or in the Studio Console to use hexgrad/Kokoro-82M via fal-ai."
        )

    client = InferenceClient(
        provider=KOKORO_PROVIDER,
        api_key=token,
    )

    # audio is returned as bytes
    audio = client.text_to_speech(
        clean_text,
        model=KOKORO_MODEL_ID,
    )

    if not audio:
        raise RuntimeError("Kokoro-82M returned an empty audio stream.")

    return bytes(audio)


async def synthesize_kokoro_tts(
    text: str,
    voice: str = "kokoro:af_heart",
    rate: str = "+0%",
) -> bytes:
    """Async wrapper for Kokoro-82M synthesis via Hugging Face InferenceClient."""
    return await asyncio.to_thread(synthesize_kokoro_sync, text)
