"""Text-to-speech synthesis and caching package."""
from app.tts.cache import AUDIO_CACHE, AudioLRUCache
from app.tts.router import get_or_synthesize_speech
from app.tts.voices import AVAILABLE_VOICES, DEFAULT_VOICE_ID

__all__ = [
    "AUDIO_CACHE",
    "AVAILABLE_VOICES",
    "AudioLRUCache",
    "DEFAULT_VOICE_ID",
    "get_or_synthesize_speech",
]
