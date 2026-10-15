"""Curated multilingual neural voices available for synthesis."""
from __future__ import annotations

from typing import Dict, List

AVAILABLE_VOICES: List[Dict[str, str]] = [
    # English
    {
        "id": "en-US-AndrewMultilingualNeural",
        "label": "Andrew (US - Warm Narrator)",
        "gender": "Male",
        "locale": "en-US",
        "language": "English",
    },
    {
        "id": "en-US-AvaMultilingualNeural",
        "label": "Ava (US - Clear & Expressive)",
        "gender": "Female",
        "locale": "en-US",
        "language": "English",
    },
    {
        "id": "en-US-AriaNeural",
        "label": "Aria (US - News & Editorial)",
        "gender": "Female",
        "locale": "en-US",
        "language": "English",
    },
    {
        "id": "en-GB-SoniaNeural",
        "label": "Sonia (UK - British Documentary)",
        "gender": "Female",
        "locale": "en-GB",
        "language": "English",
    },
    {
        "id": "en-GB-RyanNeural",
        "label": "Ryan (UK - British Conversational)",
        "gender": "Male",
        "locale": "en-GB",
        "language": "English",
    },
    {
        "id": "en-IN-NeerjaExpressiveNeural",
        "label": "Neerja (India - Expressive English)",
        "gender": "Female",
        "locale": "en-IN",
        "language": "English",
    },
    {
        "id": "en-AU-NatashaNeural",
        "label": "Natasha (Australia - Natural)",
        "gender": "Female",
        "locale": "en-AU",
        "language": "English",
    },
    # Spanish
    {
        "id": "es-ES-AlvaroNeural",
        "label": "Álvaro (Spain - Natural)",
        "gender": "Male",
        "locale": "es-ES",
        "language": "Spanish",
    },
    {
        "id": "es-ES-ElviraNeural",
        "label": "Elvira (Spain - Expressive)",
        "gender": "Female",
        "locale": "es-ES",
        "language": "Spanish",
    },
    {
        "id": "es-MX-DaliaNeural",
        "label": "Dalia (Mexico - Warm)",
        "gender": "Female",
        "locale": "es-MX",
        "language": "Spanish",
    },
    # French
    {
        "id": "fr-FR-HenriNeural",
        "label": "Henri (France - Editorial)",
        "gender": "Male",
        "locale": "fr-FR",
        "language": "French",
    },
    {
        "id": "fr-FR-DeniseNeural",
        "label": "Denise (France - Clear)",
        "gender": "Female",
        "locale": "fr-FR",
        "language": "French",
    },
    # German
    {
        "id": "de-DE-KillianNeural",
        "label": "Killian (Germany - Documentary)",
        "gender": "Male",
        "locale": "de-DE",
        "language": "German",
    },
    {
        "id": "de-DE-KatjaNeural",
        "label": "Katja (Germany - Natural)",
        "gender": "Female",
        "locale": "de-DE",
        "language": "German",
    },
    # Hindi
    {
        "id": "hi-IN-SwaraNeural",
        "label": "Swara (India - Clear Hindi)",
        "gender": "Female",
        "locale": "hi-IN",
        "language": "Hindi",
    },
    {
        "id": "hi-IN-MadhurNeural",
        "label": "Madhur (India - Warm Hindi)",
        "gender": "Male",
        "locale": "hi-IN",
        "language": "Hindi",
    },
    # Japanese
    {
        "id": "ja-JP-NanamiNeural",
        "label": "Nanami (Japan - Natural)",
        "gender": "Female",
        "locale": "ja-JP",
        "language": "Japanese",
    },
    {
        "id": "ja-JP-KeitaNeural",
        "label": "Keita (Japan - Friendly)",
        "gender": "Male",
        "locale": "ja-JP",
        "language": "Japanese",
    },
    # Chinese (Mandarin)
    {
        "id": "zh-CN-XiaoxiaoNeural",
        "label": "Xiaoxiao (China - Expressive)",
        "gender": "Female",
        "locale": "zh-CN",
        "language": "Chinese",
    },
    {
        "id": "zh-CN-YunxiNeural",
        "label": "Yunxi (China - Lively)",
        "gender": "Male",
        "locale": "zh-CN",
        "language": "Chinese",
    },
    # Italian
    {
        "id": "it-IT-DiegoNeural",
        "label": "Diego (Italy - Warm)",
        "gender": "Male",
        "locale": "it-IT",
        "language": "Italian",
    },
    {
        "id": "it-IT-ElsaNeural",
        "label": "Elsa (Italy - Expressive)",
        "gender": "Female",
        "locale": "it-IT",
        "language": "Italian",
    },
    # Portuguese
    {
        "id": "pt-BR-AntonioNeural",
        "label": "Antonio (Brazil - Natural)",
        "gender": "Male",
        "locale": "pt-BR",
        "language": "Portuguese",
    },
    {
        "id": "pt-BR-FranciscaNeural",
        "label": "Francisca (Brazil - Clear)",
        "gender": "Female",
        "locale": "pt-BR",
        "language": "Portuguese",
    },
    # Korean
    {
        "id": "ko-KR-SunHiNeural",
        "label": "Sun-Hi (Korea - Expressive)",
        "gender": "Female",
        "locale": "ko-KR",
        "language": "Korean",
    },
    {
        "id": "ko-KR-InJoonNeural",
        "label": "In-Joon (Korea - Natural)",
        "gender": "Male",
        "locale": "ko-KR",
        "language": "Korean",
    },
]

DEFAULT_VOICE_ID = "en-US-AndrewMultilingualNeural"
