"""Unit tests for Phase B: SQLite WAL database storage and PlanetScale indexing hygiene."""
from __future__ import annotations

import tempfile
from pathlib import Path
import pytest

from app.db import DatabaseManager


@pytest.fixture
def temp_db():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_theya.db"
        db = DatabaseManager(db_path=db_path)
        yield db
        db.close()


def test_db_wal_mode_and_tables(temp_db: DatabaseManager) -> None:
    mode = temp_db.get_journal_mode()
    assert mode.lower() == "wal"

    tables = temp_db.list_tables()
    assert "articles" in tables
    assert "reading_progress" in tables
    assert "feedback" in tables


def test_article_upsert_and_retrieval(temp_db: DatabaseManager) -> None:
    article_data = {
        "url": "https://example.com/test-article",
        "title": "Test Article",
        "author": "Alice",
        "sitename": "example.com",
        "date": "2026-03-01",
        "extractor_used": "tier1-trafilatura",
        "word_count": 500,
        "estimated_read_minutes": 3.0,
        "sentences_json": '[{"idx": 0, "display_text": "Hello", "speech_text": "Hello.", "kind": "title"}]',
    }
    temp_db.save_article(article_data)

    retrieved = temp_db.get_article("https://example.com/test-article")
    assert retrieved is not None
    assert retrieved["title"] == "Test Article"
    assert retrieved["word_count"] == 500


def test_progress_tracking_and_history(temp_db: DatabaseManager) -> None:
    url = "https://example.com/progress-test"
    temp_db.save_article({
        "url": url,
        "title": "Progress Test",
        "author": None,
        "sitename": "example.com",
        "date": None,
        "extractor_used": "tier1-trafilatura",
        "word_count": 300,
        "estimated_read_minutes": 1.7,
        "sentences_json": "[]",
    })

    temp_db.save_progress(url=url, last_index=15, total_sentences=50)
    progress = temp_db.get_progress(url)
    assert progress is not None
    assert progress["last_index"] == 15
    assert progress["total_sentences"] == 50

    history = temp_db.get_reading_history(limit=10)
    assert len(history) == 1
    assert history[0]["url"] == url
    assert history[0]["last_index"] == 15


def test_feedback_insertion_and_query(temp_db: DatabaseManager) -> None:
    temp_db.save_feedback({
        "rating": 5,
        "feedback_type": "general",
        "article_url": "https://example.com/good-article",
        "sentence_idx": 4,
        "comments": "Flawless pronunciation!",
        "client_ip": "127.0.0.1",
    })

    recent = temp_db.get_recent_feedback(limit=5)
    assert len(recent) == 1
    assert recent[0]["rating"] == 5
    assert recent[0]["comments"] == "Flawless pronunciation!"
