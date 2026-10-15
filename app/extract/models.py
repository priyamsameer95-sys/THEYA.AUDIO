"""Data models and errors shared across the extraction pipeline."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import List, Optional

TIER0_HTML = "tier0-client-html"
TIER1_TRAFILATURA = "tier1-trafilatura"
TIER2_JINA = "tier2-jina"


@dataclass
class Extraction:
    """The clean result of extracting one article, from any tier."""

    source_url: str
    tier: str
    title: str
    markdown: str
    byline: Optional[str] = None
    sitename: Optional[str] = None
    date: Optional[str] = None
    # Why earlier tiers were rejected, e.g. ["tier1: too_short (42 words)"].
    notes: List[str] = field(default_factory=list)

    @property
    def word_count(self) -> int:
        return len(self.markdown.split())

    def to_dict(self) -> dict:
        data = asdict(self)
        data["word_count"] = self.word_count
        return data


@dataclass
class FetchResult:
    """Raw HTTP result of a guarded fetch (after redirects)."""

    url: str
    status: int
    body: bytes
    content_type: str


class ExtractionError(Exception):
    """A user-facing failure. ``message`` is safe to show in the UI."""

    status_code = 422

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class UnsafeURLError(ExtractionError):
    """URL is malformed, uses a forbidden scheme or points at a private host."""

    status_code = 400


class FetchError(ExtractionError):
    """Network failure, timeout, oversize body or non-HTML response."""

    status_code = 502
