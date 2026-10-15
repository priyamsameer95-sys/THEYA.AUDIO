"""Sentence segmentation and boundary disambiguation using pySBD.

Parses Markdown into structured blocks (headings, code blocks, tables, prose)
and creates synchronized (display_text, speech_text) sentence units.
"""
from __future__ import annotations

import re
from typing import List

import pysbd

from app.text.models import ProcessedArticle, Sentence
from app.text.sanitize import (
    CODE_CUE_SPEECH,
    TABLE_CUE_SPEECH,
    clean_markdown_formatting,
    sanitize_prose_for_speech,
)

MAX_SENTENCE_CHARS = 420
MIN_ALPHANUM_CHARS = 2
WORDS_PER_MINUTE = 175.0

SEGMENTER = pysbd.Segmenter(language="en", clean=False)


def _pack_tokens_into_chunks(tokens: List[str], max_chars: int) -> List[str]:
    """Greedily aggregates string tokens up to max_chars."""
    chunks: List[str] = []
    current = ""
    for tok in tokens:
        tok = tok.strip()
        if not tok:
            continue
        if not current:
            current = tok
        elif len(current) + 1 + len(tok) <= max_chars:
            current = f"{current} {tok}"
        else:
            chunks.append(current)
            current = tok
    if current:
        chunks.append(current)
    return chunks


def _split_oversized_chunk(chunk: str, max_chars: int) -> List[str]:
    """Splits single oversized word sequences that lack punctuation."""
    if len(chunk) <= max_chars:
        return [chunk]
    words = chunk.split()
    return _pack_tokens_into_chunks(words, max_chars=max_chars) or [chunk]


def split_long_sentence(text: str, max_chars: int = MAX_SENTENCE_CHARS) -> List[str]:
    """Ensures no sentence chunk exceeds max_chars.

    First tries splitting on semicolons (;) or em-dashes (—).
    If a part is still too long, splits on commas (, ) or word boundaries.
    """
    if len(text) <= max_chars:
        return [text]

    # Level 1: split on semicolons or dashes
    parts = [p.strip() for p in re.split(r"(?<=[;—])\s+|\s+—\s+", text) if p.strip()]
    refined: List[str] = []

    for part in parts:
        if len(part) <= max_chars:
            refined.append(part)
            continue

        # Level 2: split on commas with lookbehind
        sub_parts = re.split(r"(?<=,)\s+", part)
        comma_chunks = _pack_tokens_into_chunks(sub_parts, max_chars=max_chars)

        # Level 3: split any remaining oversized chunks on words
        for chunk in comma_chunks:
            refined.extend(_split_oversized_chunk(chunk, max_chars=max_chars))

    return refined or [text]



def has_meaningful_content(text: str) -> bool:
    """True if text has at least MIN_ALPHANUM_CHARS alphanumeric characters."""
    return len(re.findall(r"[A-Za-z0-9]", text)) >= MIN_ALPHANUM_CHARS


def process_markdown_to_sentences(markdown: str, title: str = "") -> List[Sentence]:
    """Converts extracted Markdown into an array of indexed Sentence units."""
    sentences: List[Sentence] = []
    idx = 0

    # 1. Article Title as Sentence 0
    if title and title.strip():
        clean_title = sanitize_prose_for_speech(title)
        if clean_title and not clean_title.endswith((".", "!", "?")):
            clean_title += "."
        if has_meaningful_content(clean_title):
            sentences.append(
                Sentence(
                    idx=idx,
                    display_text=title.strip(),
                    speech_text=clean_title,
                    kind="title",
                )
            )
            idx += 1

    # 2. Block Tokenization: Code blocks, Tables, Headings, and Prose paragraphs
    lines = markdown.splitlines()
    i = 0
    total_lines = len(lines)

    while i < total_lines:
        line = lines[i]
        stripped = line.strip()

        if not stripped:
            i += 1
            continue

        # --- A. Code Block (```) ---
        if stripped.startswith("```"):
            code_lines = [line]
            i += 1
            while i < total_lines and not lines[i].strip().startswith("```"):
                code_lines.append(lines[i])
                i += 1
            if i < total_lines:
                code_lines.append(lines[i])
                i += 1
            raw_code = "\n".join(code_lines)
            sentences.append(
                Sentence(
                    idx=idx,
                    display_text=raw_code,
                    speech_text=CODE_CUE_SPEECH,
                    kind="code_cue",
                )
            )
            idx += 1
            continue

        # --- B. Table (|...|) ---
        if stripped.startswith("|") and stripped.endswith("|"):
            table_lines = [line]
            i += 1
            while i < total_lines and lines[i].strip().startswith("|") and lines[i].strip().endswith("|"):
                table_lines.append(lines[i])
                i += 1
            raw_table = "\n".join(table_lines)
            sentences.append(
                Sentence(
                    idx=idx,
                    display_text=raw_table,
                    speech_text=TABLE_CUE_SPEECH,
                    kind="table_cue",
                )
            )
            idx += 1
            continue

        # --- C. Heading (### Heading) ---
        if stripped.startswith("#"):
            heading_text = re.sub(r"^#{1,6}\s+", "", stripped)
            heading_speech = sanitize_prose_for_speech(heading_text)
            if not heading_speech.endswith((".", "!", "?")):
                heading_speech += "."
            if has_meaningful_content(heading_speech):
                sentences.append(
                    Sentence(
                        idx=idx,
                        display_text=heading_text,
                        speech_text=heading_speech,
                        kind="heading",
                    )
                )
                idx += 1
            i += 1
            continue

        # --- D. Prose Paragraph ---
        para_lines = [line]
        i += 1
        while (
            i < total_lines
            and lines[i].strip()
            and not lines[i].strip().startswith("```")
            and not (lines[i].strip().startswith("|") and lines[i].strip().endswith("|"))
            and not lines[i].strip().startswith("#")
        ):
            para_lines.append(lines[i])
            i += 1

        paragraph = " ".join(para_lines).strip()
        segments = SEGMENTER.segment(paragraph)

        for seg in segments:
            seg = seg.strip()
            if not seg:
                continue

            # Length guardrail split
            sub_segments = split_long_sentence(seg, max_chars=MAX_SENTENCE_CHARS)
            for sub in sub_segments:
                sub = sub.strip()
                speech = sanitize_prose_for_speech(sub)
                if not has_meaningful_content(speech):
                    continue

                display = clean_markdown_formatting(sub)
                sentences.append(
                    Sentence(
                        idx=idx,
                        display_text=display,
                        speech_text=speech,
                        kind="prose",
                    )
                )
                idx += 1

    # 3. Deduplicate consecutive identical sentences (e.g. repeated title / H1)
    deduped: List[Sentence] = []
    current_idx = 0
    for s in sentences:
        if (
            deduped
            and deduped[-1].speech_text.lower().rstrip(".") == s.speech_text.lower().rstrip(".")
        ):
            continue
        s.idx = current_idx
        deduped.append(s)
        current_idx += 1

    return deduped


def create_processed_article(
    url: str,
    title: str,
    markdown: str,
    extractor_used: str,
    byline: str = None,
    sitename: str = None,
    date: str = None,
) -> ProcessedArticle:
    """Full pipeline from extracted article to ProcessedArticle."""
    sentences = process_markdown_to_sentences(markdown, title=title)
    total_words = sum(len(s.speech_text.split()) for s in sentences)
    est_mins = max(0.5, round(total_words / WORDS_PER_MINUTE, 1))

    return ProcessedArticle(
        url=url,
        title=title,
        extractor_used=extractor_used,
        word_count=total_words,
        estimated_read_minutes=est_mins,
        sentences=sentences,
        byline=byline,
        sitename=sitename,
        date=date,
    )
