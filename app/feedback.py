"""User feedback storage and reporting."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
FEEDBACK_FILE = DATA_DIR / "feedback.jsonl"


class FeedbackRequest(BaseModel):
    rating: int = Field(..., ge=1, le=5, description="Star rating between 1 and 5")
    feedback_type: str = Field(
        "general",
        description="Category: general | extraction_issue | audio_quality | pronunciation",
    )
    article_url: Optional[str] = Field(None, description="URL of the article if applicable")
    sentence_idx: Optional[int] = Field(None, description="Sentence index if specific to a sentence")
    comments: Optional[str] = Field(None, max_length=1000, description="User comments or notes")


def save_feedback(data: FeedbackRequest, client_ip: str = "127.0.0.1") -> Dict[str, Any]:
    """Saves feedback entry to SQLite database storage."""
    from app.db import DB
    return DB.save_feedback({
        "rating": data.rating,
        "feedback_type": data.feedback_type,
        "article_url": data.article_url,
        "sentence_idx": data.sentence_idx,
        "comments": data.comments,
        "client_ip": client_ip,
    })


def get_recent_feedback(limit: int = 50) -> List[Dict[str, Any]]:
    """Returns the most recent feedback entries from SQLite."""
    from app.db import DB
    return DB.get_recent_feedback(limit=limit)
