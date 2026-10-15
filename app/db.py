"""SQLite WAL Database Storage with PlanetScale-inspired Schema & Indexing Hygiene."""
from __future__ import annotations

import json
from pathlib import Path
import sqlite3
from typing import Any, Dict, List, Optional

DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "theya.db"


class DatabaseManager:
    """Manages SQLite storage in WAL mode for high-concurrency article and feedback storage."""

    def __init__(self, db_path: Optional[Path] = None) -> None:
        self.db_path = db_path or DEFAULT_DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(
            str(self.db_path),
            check_same_thread=False,
            timeout=10.0,
        )
        self._conn.row_factory = sqlite3.Row
        self._init_db()

    def _init_db(self) -> None:
        with self._conn:
            # Enable WAL mode and foreign key enforcement
            self._conn.execute("PRAGMA journal_mode = WAL;")
            self._conn.execute("PRAGMA synchronous = NORMAL;")
            self._conn.execute("PRAGMA foreign_keys = ON;")

            # 1. Articles table
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS articles (
                    url TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    author TEXT,
                    sitename TEXT,
                    date TEXT,
                    extractor_used TEXT NOT NULL,
                    word_count INTEGER NOT NULL,
                    estimated_read_minutes REAL NOT NULL,
                    sentences_json TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
            # Composite index for chronological queries
            self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_articles_updated ON articles(updated_at DESC);"
            )

            # 2. Reading progress table
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS reading_progress (
                    url TEXT PRIMARY KEY,
                    last_index INTEGER NOT NULL DEFAULT 0,
                    total_sentences INTEGER NOT NULL DEFAULT 0,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (url) REFERENCES articles(url) ON DELETE CASCADE
                );
                """
            )
            self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_progress_updated ON reading_progress(updated_at DESC);"
            )

            # 3. Feedback table
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS feedback (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    rating INTEGER NOT NULL,
                    feedback_type TEXT NOT NULL,
                    article_url TEXT,
                    sentence_idx INTEGER,
                    comments TEXT,
                    client_ip TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
            self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_feedback_rating_time ON feedback(rating, timestamp DESC);"
            )

    def get_journal_mode(self) -> str:
        cursor = self._conn.execute("PRAGMA journal_mode;")
        row = cursor.fetchone()
        return row[0] if row else ""

    def list_tables(self) -> List[str]:
        cursor = self._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';"
        )
        return [row[0] for row in cursor.fetchall()]

    def save_article(self, data: Dict[str, Any]) -> None:
        """Upserts an article record."""
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO articles (
                    url, title, author, sitename, date, extractor_used,
                    word_count, estimated_read_minutes, sentences_json, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(url) DO UPDATE SET
                    title=excluded.title,
                    author=excluded.author,
                    sitename=excluded.sitename,
                    date=excluded.date,
                    extractor_used=excluded.extractor_used,
                    word_count=excluded.word_count,
                    estimated_read_minutes=excluded.estimated_read_minutes,
                    sentences_json=excluded.sentences_json,
                    updated_at=CURRENT_TIMESTAMP;
                """,
                (
                    data["url"],
                    data["title"],
                    data.get("author"),
                    data.get("sitename"),
                    data.get("date"),
                    data["extractor_used"],
                    data["word_count"],
                    data["estimated_read_minutes"],
                    data["sentences_json"],
                ),
            )

    def get_article(self, url: str) -> Optional[Dict[str, Any]]:
        cursor = self._conn.execute("SELECT * FROM articles WHERE url = ?;", (url,))
        row = cursor.fetchone()
        return dict(row) if row else None

    def save_progress(self, url: str, last_index: int, total_sentences: int) -> None:
        """Upserts reading progress for a given article URL."""
        with self._conn:
            # Ensure stub article exists to satisfy foreign key
            self._conn.execute(
                """
                INSERT OR IGNORE INTO articles (
                    url, title, extractor_used, word_count, estimated_read_minutes, sentences_json
                ) VALUES (?, ?, 'pending', 0, 0, '[]');
                """,
                (url, url),
            )
            self._conn.execute(
                """
                INSERT INTO reading_progress (url, last_index, total_sentences, updated_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(url) DO UPDATE SET
                    last_index=excluded.last_index,
                    total_sentences=excluded.total_sentences,
                    updated_at=CURRENT_TIMESTAMP;
                """,
                (url, last_index, total_sentences),
            )

    def update_progress(
        self, url: str, current_sentence_idx: int, total_sentences: int
    ) -> Dict[str, Any]:
        """Updates progress and returns calculated completion metrics."""
        self.save_progress(url=url, last_index=current_sentence_idx, total_sentences=total_sentences)
        ratio = round(current_sentence_idx / max(1, total_sentences), 2)
        is_completed = current_sentence_idx >= max(0, total_sentences - 1)
        return {
            "url": url,
            "current_sentence_idx": current_sentence_idx,
            "total_sentences": total_sentences,
            "completion_ratio": ratio,
            "is_completed": is_completed,
        }

    def get_progress(self, url: str) -> Optional[Dict[str, Any]]:
        cursor = self._conn.execute("SELECT * FROM reading_progress WHERE url = ?;", (url,))
        row = cursor.fetchone()
        return dict(row) if row else None

    def get_reading_history(self, limit: int = 25) -> List[Dict[str, Any]]:
        """Returns recent reading history joined with article metadata using keyset-friendly sorting."""
        cursor = self._conn.execute(
            """
            SELECT 
                a.url, a.title, a.sitename, a.word_count, a.estimated_read_minutes,
                COALESCE(p.last_index, 0) as last_index,
                COALESCE(p.total_sentences, 0) as total_sentences,
                COALESCE(p.updated_at, a.updated_at) as last_read_at
            FROM articles a
            LEFT JOIN reading_progress p ON a.url = p.url
            ORDER BY last_read_at DESC
            LIMIT ?;
            """,
            (limit,),
        )
        results = []
        for row in cursor.fetchall():
            d = dict(row)
            tot = d["total_sentences"]
            idx = d["last_index"]
            d["completion_ratio"] = round(idx / max(1, tot), 2) if tot > 0 else 0.0
            d["is_completed"] = 1 if (tot > 0 and idx >= tot - 1) else 0
            results.append(d)
        return results


    def save_feedback(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Inserts a user feedback record."""
        with self._conn:
            cursor = self._conn.execute(
                """
                INSERT INTO feedback (rating, feedback_type, article_url, sentence_idx, comments, client_ip)
                VALUES (?, ?, ?, ?, ?, ?);
                """,
                (
                    data["rating"],
                    data["feedback_type"],
                    data.get("article_url"),
                    data.get("sentence_idx"),
                    data.get("comments"),
                    data.get("client_ip", "127.0.0.1"),
                ),
            )
            feedback_id = cursor.lastrowid
        return {**data, "id": feedback_id}

    def get_recent_feedback(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Returns recent user feedback records ordered chronologically (latest at the end)."""
        cursor = self._conn.execute(
            "SELECT * FROM (SELECT * FROM feedback ORDER BY id DESC LIMIT ?) ORDER BY id ASC;",
            (limit,),
        )
        return [dict(row) for row in cursor.fetchall()]

    def close(self) -> None:
        self._conn.close()


# Global database singleton
DB = DatabaseManager()
