"""Unit tests for Phase 2: text sanitization and pySBD sentence segmentation."""
from __future__ import annotations

from app.text.sanitize import (
    CODE_CUE_SPEECH,
    TABLE_CUE_SPEECH,
    clean_markdown_formatting,
    sanitize_prose_for_speech,
)
from app.text.segment import (
    MAX_SENTENCE_CHARS,
    create_processed_article,
    process_markdown_to_sentences,
    split_long_sentence,
)


def test_sanitize_strips_images_before_links() -> None:
    """Regression test for Bug B2: ![Alt](url) must not become !Alt."""
    raw = "Here is an image ![System Architecture Diagram](https://example.com/diag.png) and a link [Read More](https://example.com/more)."
    cleaned = sanitize_prose_for_speech(raw)
    assert "![" not in cleaned
    assert "!System Architecture Diagram" not in cleaned
    assert "System Architecture Diagram" not in cleaned
    assert "Read More" in cleaned


def test_pysbd_preserves_abbreviations_and_decimals() -> None:
    """pySBD must not chop abbreviations or decimals into broken sentences."""
    text = "On Jan. 5, Dr. Sarah Smith paid $4.99 in the U.S. for a book. She loved it!"
    sentences = process_markdown_to_sentences(text, title="Book Review")

    assert len(sentences) == 3
    assert sentences[0].speech_text == "Book Review."
    assert sentences[1].speech_text == "On Jan. 5, Dr. Sarah Smith paid $4.99 in the U.S. for a book."
    assert sentences[2].speech_text == "She loved it!"


def test_code_blocks_and_tables_emit_spoken_cues() -> None:
    """Regression test for Bug B1: code blocks & tables generate spoken cues."""
    markdown = """
# Quick Tutorial

Here is the setup:

```python
import httpx
print("Hello world")
```

| Method | Status |
|---|---|
| GET | 200 |

Done reading!
"""
    sentences = process_markdown_to_sentences(markdown, title="Tutorial")
    speech_texts = [s.speech_text for s in sentences]

    assert CODE_CUE_SPEECH in speech_texts
    assert TABLE_CUE_SPEECH in speech_texts
    # Display text still contains the original code & table
    code_sentence = next(s for s in sentences if s.kind == "code_cue")
    assert "print(\"Hello world\")" in code_sentence.display_text
    table_sentence = next(s for s in sentences if s.kind == "table_cue")
    assert "GET | 200" in table_sentence.display_text


def test_long_sentence_guardrail_splits_cleanly() -> None:
    """Regression test for Bug B3: run-on sentences without ; or — must be split safely <= MAX_SENTENCE_CHARS."""
    run_on = (
        "When you consider the vast and intricate mechanisms of modern computer networking, "
        "including packet switching, routing protocols, border gateway synchronization, domain name resolution, "
        "transmission control handshakes, cryptographic key exchanges, transport layer security ciphers, "
        "buffer pool allocations, cache invalidation strategies, content delivery network edges, "
        "and client rendering pipelines, it becomes wonderfully apparent that thousands of separate engineering achievements "
        "must collaborate harmoniously every single time an end user clicks a hyperlink on the web."
    )
    assert len(run_on) > MAX_SENTENCE_CHARS

    chunks = split_long_sentence(run_on, max_chars=MAX_SENTENCE_CHARS)
    assert len(chunks) > 1
    for chunk in chunks:
        assert len(chunk) <= MAX_SENTENCE_CHARS


def test_snake_case_preserved() -> None:
    """Variables like extract_with_trafilatura should not lose underscores inside words."""
    text = "We use extract_with_trafilatura and async_io_loop in this function."
    cleaned = sanitize_prose_for_speech(text)
    assert "extract_with_trafilatura" in cleaned
    assert "async_io_loop" in cleaned


def test_title_and_h1_deduplication() -> None:
    """Consecutive identical sentences (e.g. metadata title and article h1) are deduplicated."""
    markdown = """# How to Do Great Work\n\nHow to Do Great Work.\n\nFirst paragraph of the essay."""
    sentences = process_markdown_to_sentences(markdown, title="How to Do Great Work")
    assert sentences[0].speech_text == "How to Do Great Work."
    # The duplicate H1 is not repeated as a second identical sentence
    assert sentences[1].speech_text == "First paragraph of the essay."
