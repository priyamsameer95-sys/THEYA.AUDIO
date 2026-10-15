"""Unit and regression tests for Document Extraction and Podcast Cadence Engine."""
from __future__ import annotations

import io
import pytest
import docx
from fastapi.testclient import TestClient

from app.main import app
from app.extract.document import extract_document
from app.podcast.cadence import analyze_sentence_cadence, shape_article_into_podcast


def test_cadence_sentence_analysis() -> None:
    # 1. Question sentence
    disp, spch, pause_ms, mood = analyze_sentence_cadence("Why does human pacing matter?", 1)
    assert mood == "question"
    assert pause_ms >= 500

    # 2. Revelation sentence
    disp2, spch2, pause_ms2, mood2 = analyze_sentence_cadence("The truth is, without pauses speech feels robotic.", 2)
    assert mood2 == "revelation"
    assert "<break" in spch2

    # 3. Em-dash and colon pauses
    disp3, spch3, _, _ = analyze_sentence_cadence("Here is the key: audiobooks need cadence — natural breathing.", 3)
    assert "<break time=" in spch3


def test_cadence_punchy_and_enumeration() -> None:
    # 1. Enumeration sentence
    disp, spch, pause_ms, mood = analyze_sentence_cadence("First, let us examine the acoustic foundation.", 1)
    assert mood == "enumeration"
    assert pause_ms >= 300

    # 2. Punchy takeaway
    disp2, spch2, pause_ms2, mood2 = analyze_sentence_cadence("It worked.", 2)
    assert mood2 == "punchy"
    assert pause_ms2 >= 450

    # 3. Parenthetical aside
    disp3, spch3, _, _ = analyze_sentence_cadence("The soundscape (which is procedural) brings warmth.", 3)
    assert "— which is procedural —" in disp3


def test_document_extract_docx() -> None:
    doc = docx.Document()
    doc.add_heading("Architecture of Sound", level=1)
    doc.add_paragraph("First paragraph discussing acoustic design.")
    doc.add_paragraph("Second paragraph explaining frequency analysis.")

    buf = io.BytesIO()
    doc.save(buf)
    buf.seek(0)

    title, paras = extract_document("architecture.docx", buf.read())
    assert title == "Architecture of Sound"
    assert len(paras) == 2


def test_document_extract_pdf_fallback() -> None:
    import pypdf
    writer = pypdf.PdfWriter()
    writer.add_blank_page(width=200, height=200)
    buf = io.BytesIO()
    writer.write(buf)
    buf.seek(0)

    title, paras = extract_document("test_doc.pdf", buf.read())
    assert "Test Doc" in title
    assert isinstance(paras, list)


def test_api_extract_text_podcast_mode() -> None:
    client = TestClient(app)
    text = (
        "# Why Podcasting Works\n\n"
        "Podcasting is about intimacy and pacing. Why does a voice sound real?\n\n"
        "In fact, human speech pauses. Think about it: without silence, words lose meaning.\n\n"
        "First, cadence sets the rhythm. It worked."
    )
    res = client.post("/api/extract/text", json={
        "text": text,
        "title": "Why Podcasting Works",
        "podcast_mode": True,
    })
    assert res.status_code == 200
    data = res.json()
    assert "Why Podcasting Works" in data["title"]
    assert len(data["sentences"]) >= 5
    assert any(s["mood"] == "question" for s in data["sentences"])
    assert any(s["mood"] == "revelation" for s in data["sentences"])
    assert any(s["mood"] == "punchy" for s in data["sentences"])


def test_api_extract_file_markdown() -> None:
    client = TestClient(app)
    file_bytes = io.BytesIO(b"# Monograph on Taste\n\nParagraph one.\n\nParagraph two.")
    res = client.post(
        "/api/extract/file",
        files={"file": ("taste.md", file_bytes, "text/markdown")},
        data={"podcast_mode": "true"},
    )
    assert res.status_code == 200
    data = res.json()
    assert "Monograph on Taste" in data["title"]
    assert len(data["sentences"]) >= 2


def test_extract_document_rejects_raw_image() -> None:
    with pytest.raises(ValueError, match="requires OCR processing"):
        extract_document("screenshot.png", b"\x89PNG\r\n\x1a\n...")
