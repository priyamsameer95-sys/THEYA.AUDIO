"""TTS sanitization pipeline for clean speech synthesis."""
from __future__ import annotations

import re

# RegEx patterns for speech cleanup
RE_CODE_BLOCK = re.compile(r"```[\s\S]*?```")
RE_TABLE = re.compile(r"(?m)^\s*\|.*\|\s*$")
RE_IMAGE = re.compile(r"!\[[^\]]*\]\([^\)]+\)")  # Step 1: strip images before links!
RE_LINK = re.compile(r"\[([^\]]+)\]\((?:https?://|/|\#)[^\)]+\)")
RE_URL = re.compile(r"https?://\S+")
RE_CITATION = re.compile(r"\[\s*(?:\d+|[a-zA-Z]|citation needed)\s*\]|\^\d+")
RE_HEADING = re.compile(r"(?m)^\s*#{1,6}\s+")
RE_BLOCKQUOTE = re.compile(r"(?m)^\s*>\s?")
RE_BOLD_ITALIC_ASTERISK = re.compile(r"\*{1,3}")
# Underscore markdown emphasis: _word_ or __word__ without affecting snake_case
RE_UNDERSCORE_EMPHASIS = re.compile(r"(^|\s)_([^_]+)_(?=\s|$|[.,!?;:])")
RE_INLINE_CODE = re.compile(r"`([^`]+)`")
RE_HTML_TAGS = re.compile(r"<[^>]+>")
RE_MULTI_SPACES = re.compile(r"[ \t]+")
RE_MULTI_NEWLINES = re.compile(r"\n{2,}")

CODE_CUE_SPEECH = "Code block skipped for audio playback."
TABLE_CUE_SPEECH = "Table skipped for audio playback."


def clean_markdown_formatting(text: str) -> str:
    """Strips Markdown syntax leaving readable text for display."""
    # Step 1: Strip images before converting links
    s = RE_IMAGE.sub(" ", text)
    # Step 2: Convert links [Text](url) -> Text
    s = RE_LINK.sub(r"\1", s)
    # Step 3: Strip inline code backticks but preserve content
    s = RE_INLINE_CODE.sub(r"\1", s)
    # Step 4: Remove remaining HTML tags
    s = RE_HTML_TAGS.sub(" ", s)
    # Step 5: Normalize spaces
    s = RE_MULTI_SPACES.sub(" ", s)
    return s.strip()


def sanitize_prose_for_speech(text: str) -> str:
    """Sanitizes regular prose text for the TTS engine.

    Fixes:
    - B2: images stripped before links.
    - Raw URLs replaced with 'link'.
    - Citations like [12] removed.
    - Markdown headings, quotes, asterisks stripped.
    - Preserves underscores in snake_case identifiers.
    """
    s = text
    # 1. Strip images first
    s = RE_IMAGE.sub(" ", s)
    # 2. Convert markdown links
    s = RE_LINK.sub(r"\1", s)
    # 3. Replace raw URLs with "link"
    s = RE_URL.sub(" link ", s)
    # 4. Strip citations [1], [12], [citation needed]
    s = RE_CITATION.sub("", s)
    # 5. Strip Markdown structural markers
    s = RE_HEADING.sub("", s)
    s = RE_BLOCKQUOTE.sub("", s)
    s = RE_INLINE_CODE.sub(r"\1", s)
    s = RE_HTML_TAGS.sub(" ", s)
    # 6. Asterisks and underscore formatting (keep snake_case intact)
    s = RE_BOLD_ITALIC_ASTERISK.sub("", s)
    s = RE_UNDERSCORE_EMPHASIS.sub(r"\1\2", s)
    # 7. Normalize whitespace
    s = RE_MULTI_SPACES.sub(" ", s)
    return s.strip()
