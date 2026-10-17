"""Data structures for sanitized sentences and processed articles."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import List, Optional


@dataclass
class Sentence:
    """A single unit of playback and highlighting.

    Carries two versions of the text:
    - display_text: rendered in the reader view
    - speech_text: passed to the TTS synthesis engine
    """

    idx: int
    display_text: str
    speech_text: str
    kind: str = "prose"  # "title", "heading", "prose", "code_cue", "table_cue"
    pause_after_ms: int = 250
    mood: str = "narrative"
    speaker: Optional[str] = None
    speaker_name: Optional[str] = None
    voice_id: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ProcessedArticle:
    """An extracted article processed into sentences ready for UI & audio."""

    url: str
    title: str
    extractor_used: str
    word_count: int
    estimated_read_minutes: float
    sentences: List[Sentence]
    byline: Optional[str] = None
    sitename: Optional[str] = None
    date: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "url": self.url,
            "title": self.title,
            "author": self.byline,
            "sitename": self.sitename,
            "date": self.date,
            "extractor_used": self.extractor_used,
            "word_count": self.word_count,
            "estimated_read_minutes": self.estimated_read_minutes,
            "sentences": [s.to_dict() for s in self.sentences],
        }
