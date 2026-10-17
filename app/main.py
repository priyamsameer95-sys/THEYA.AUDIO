"""theya.voice: Web-to-Speech Platform Backend.

Extracts clean article prose from any webpage (skipping navbars, footers,
sitemaps, and ads) and streams neural TTS sentence-by-sentence with sub-second latency.
"""
from __future__ import annotations

import io
import logging
from pathlib import Path
from typing import List, Optional

import re
import hashlib
from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, HttpUrl

from app import config
from app.db import DB
from app.extract import ExtractionError, extract_article
from app.feedback import FeedbackRequest
from app.text import create_processed_article
from app.tts import AVAILABLE_VOICES, DEFAULT_VOICE_ID, get_or_synthesize_speech

logger = logging.getLogger("theya.main")


BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"

app = FastAPI(
    title="theya.voice API",
    description="Turns any webpage into a clean, sentence-highlighted audio stream.",
    version="0.1.0",
)


class ExtractRequest(BaseModel):
    url: HttpUrl = Field(..., description="The full HTTP/HTTPS URL of the article.")
    html: Optional[str] = Field(None, description="Optional raw HTML (Tier 0 bookmarklet).")
    dialogue_mode: bool = Field(False, description="Convert article into 2-person Cognitive Focus Dialogue")
    voice_a: str = Field(DEFAULT_VOICE_ID, description="Anchor Voice ID (Speaker A)")
    voice_b: str = Field("en-US-AvaMultilingualNeural", description="Focus Partner Voice ID (Speaker B)")


class ProgressRequest(BaseModel):
    url: str = Field(..., description="The URL of the article")
    current_sentence_idx: int = Field(..., ge=0, description="Current sentence index")
    total_sentences: int = Field(..., ge=1, description="Total sentence count")


class SentenceModel(BaseModel):
    idx: int
    display_text: str
    speech_text: str
    kind: str
    pause_after_ms: Optional[int] = 250
    mood: Optional[str] = "narrative"
    speaker: Optional[str] = None
    speaker_name: Optional[str] = None
    voice_id: Optional[str] = None


class TextExtractRequest(BaseModel):
    text: str = Field(..., min_length=5, description="Pasted document or podcast script text")
    title: Optional[str] = Field("Pasted Monograph", description="Document title")
    podcast_mode: bool = Field(True, description="Enable podcast cadence, pauses, and dramatic inflection")
    dialogue_mode: bool = Field(False, description="Enable 2-person Cognitive Focus Dialogue")
    voice_a: str = Field(DEFAULT_VOICE_ID, description="Anchor Voice ID (Speaker A)")
    voice_b: str = Field("en-US-AvaMultilingualNeural", description="Focus Partner Voice ID (Speaker B)")


class ExtractResponse(BaseModel):
    url: str
    title: str
    author: Optional[str] = None
    sitename: Optional[str] = None
    date: Optional[str] = None
    extractor_used: str
    word_count: int
    estimated_read_minutes: float
    sentences: List[SentenceModel]


@app.get("/api/voices")
async def get_voices():
    """Returns curated high-naturalness neural voices for the UI."""
    return {"voices": AVAILABLE_VOICES}


@app.post("/api/extract", response_model=ExtractResponse)
async def extract_and_process(request: ExtractRequest) -> ExtractResponse:
    """Extracts clean article text from URL and splits it into TTS sentences."""
    target_url = str(request.url)
    if not request.html:
        cached = DB.get_article(target_url)
        if cached and not str(cached.get("extractor_used", "")).endswith("_dialogue"):
            import json
            sentences_data = json.loads(cached["sentences_json"])
            if not request.dialogue_mode:
                return ExtractResponse(
                    url=cached["url"],
                    title=cached["title"],
                    author=cached.get("author"),
                    sitename=cached.get("sitename"),
                    date=cached.get("date"),
                    extractor_used=cached["extractor_used"],
                    word_count=cached["word_count"],
                    estimated_read_minutes=cached["estimated_read_minutes"],
                    sentences=[SentenceModel(**s) for s in sentences_data],
                )
            else:
                from app.podcast.dialogue import _is_boilerplate, shape_article_into_dialogue
                prose_sents = [
                    s["display_text"]
                    for s in sentences_data
                    if s.get("kind") == "prose"
                    and s.get("display_text")
                    and not _is_boilerplate(s["display_text"])
                ]
                paragraphs: List[str] = []
                for i in range(0, len(prose_sents), 2):
                    paragraphs.append(" ".join(prose_sents[i : i + 2]))
                dialogue_sents = shape_article_into_dialogue(
                    title=cached["title"],
                    paragraphs=paragraphs,
                    voice_a=request.voice_a,
                    voice_b=request.voice_b,
                )
                return ExtractResponse(
                    url=cached["url"],
                    title=cached["title"],
                    author=cached.get("author"),
                    sitename=cached.get("sitename"),
                    date=cached.get("date"),
                    extractor_used=f"{cached['extractor_used']}_dialogue",
                    word_count=cached["word_count"],
                    estimated_read_minutes=cached["estimated_read_minutes"],
                    sentences=[SentenceModel(**s) for s in dialogue_sents],
                )

    try:
        raw_extraction = await extract_article(url=target_url, html=request.html)
    except ExtractionError as exc:
        cached = DB.get_article(target_url)
        if cached and not request.dialogue_mode:
            import json
            sentences_data = json.loads(cached["sentences_json"])
            return ExtractResponse(
                url=cached["url"],
                title=cached["title"],
                author=cached.get("author"),
                sitename=cached.get("sitename"),
                date=cached.get("date"),
                extractor_used=cached["extractor_used"],
                word_count=cached["word_count"],
                estimated_read_minutes=cached["estimated_read_minutes"],
                sentences=[SentenceModel(**s) for s in sentences_data],
            )
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    except Exception as exc:
        cached = DB.get_article(target_url)
        if cached and not request.dialogue_mode:
            import json
            sentences_data = json.loads(cached["sentences_json"])
            return ExtractResponse(
                url=cached["url"],
                title=cached["title"],
                author=cached.get("author"),
                sitename=cached.get("sitename"),
                date=cached.get("date"),
                extractor_used=cached["extractor_used"],
                word_count=cached["word_count"],
                estimated_read_minutes=cached["estimated_read_minutes"],
                sentences=[SentenceModel(**s) for s in sentences_data],
            )
        logger.exception("Unexpected error extracting %s: %s", target_url, exc)
        raise HTTPException(
            status_code=500, detail="An unexpected error occurred while extracting the page."
        ) from exc

    processed = create_processed_article(
        url=raw_extraction.source_url,
        title=raw_extraction.title,
        markdown=raw_extraction.markdown,
        extractor_used=raw_extraction.tier,
        byline=raw_extraction.byline,
        sitename=raw_extraction.sitename,
        date=raw_extraction.date,
    )

    if not processed.sentences:
        raise HTTPException(
            status_code=422,
            detail="The page was fetched, but no pronounceable sentences remained after filtering.",
        )

    # Persist base article to history database so toggling dialogue mode on/off is instant
    try:
        import json
        sentences_payload = json.dumps([s.to_dict() for s in processed.sentences])
        DB.save_article({
            "url": processed.url,
            "title": processed.title,
            "author": processed.byline,
            "sitename": processed.sitename,
            "date": processed.date,
            "extractor_used": processed.extractor_used,
            "word_count": processed.word_count,
            "estimated_read_minutes": processed.estimated_read_minutes,
            "sentences_json": sentences_payload,
        })
    except Exception as exc:
        logger.warning("Could not persist article to history: %s", exc)

    if request.dialogue_mode:
        from app.podcast.dialogue import _is_boilerplate, shape_article_into_dialogue

        prose_sents = [
            s.display_text
            for s in processed.sentences
            if s.kind == "prose" and s.display_text and not _is_boilerplate(s.display_text)
        ]
        paragraphs = []
        for i in range(0, len(prose_sents), 2):
            paragraphs.append(" ".join(prose_sents[i : i + 2]))
        dialogue_sents = shape_article_into_dialogue(
            title=processed.title,
            paragraphs=paragraphs,
            voice_a=request.voice_a,
            voice_b=request.voice_b,
        )
        return ExtractResponse(
            url=processed.url,
            title=processed.title,
            author=processed.byline,
            sitename=processed.sitename,
            date=processed.date,
            extractor_used=f"{processed.extractor_used}_dialogue",
            word_count=processed.word_count,
            estimated_read_minutes=processed.estimated_read_minutes,
            sentences=[SentenceModel(**s) for s in dialogue_sents],
        )

    return ExtractResponse(**processed.to_dict())


@app.post("/api/extract/text", response_model=ExtractResponse)
async def extract_text_endpoint(req: TextExtractRequest) -> ExtractResponse:
    """Ingests pasted text or notes and converts them into a podcast or 2-person dialogue script."""
    from app.extract.document import extract_from_text
    from app.podcast.cadence import shape_article_into_podcast
    from app.podcast.dialogue import shape_article_into_dialogue

    title, paragraphs = extract_from_text(req.text, fallback_title=req.title or "Pasted Monograph")
    if not paragraphs:
        paragraphs = [req.text.strip()]

    content_hash = hashlib.sha256(req.text.encode()).hexdigest()[:12]
    doc_url = f"text://pasted/{content_hash}"

    if req.dialogue_mode:
        podcast_sents = shape_article_into_dialogue(
            title, paragraphs, voice_a=req.voice_a, voice_b=req.voice_b
        )
        extractor_label = "dialogue_text"
    elif req.podcast_mode:
        podcast_sents = shape_article_into_podcast(title, paragraphs)
        extractor_label = "podcast_text"
    else:
        from app.text import create_processed_article
        markdown_body = "\n\n".join(paragraphs)
        processed = create_processed_article(
            url=doc_url,
            title=title,
            markdown=markdown_body,
            extractor_used="pasted_text",
        )
        podcast_sents = [s.to_dict() for s in processed.sentences]
        extractor_label = "pasted_text"

    word_count = sum(len(p.split()) for p in paragraphs)
    est_minutes = max(0.5, round(word_count / 155.0, 1))

    import json
    sentences_payload = json.dumps(podcast_sents)
    try:
        DB.save_article({
            "url": doc_url,
            "title": title,
            "author": "Focus Dialogue" if req.dialogue_mode else "Pasted Notes",
            "sitename": "they.audio Focus Studio" if req.dialogue_mode else "they.audio Podcast",
            "date": None,
            "extractor_used": extractor_label,
            "word_count": word_count,
            "estimated_read_minutes": est_minutes,
            "sentences_json": sentences_payload,
        })
    except Exception as exc:
        logger.warning("Could not persist pasted text to DB: %s", exc)

    return ExtractResponse(
        url=doc_url,
        title=title,
        author="Focus Dialogue" if req.dialogue_mode else "Pasted Notes",
        sitename="they.audio Focus Studio" if req.dialogue_mode else "they.audio Podcast",
        date=None,
        extractor_used=extractor_label,
        word_count=word_count,
        estimated_read_minutes=est_minutes,
        sentences=[SentenceModel(**s) for s in podcast_sents],
    )


@app.post("/api/extract/file", response_model=ExtractResponse)
async def extract_file_endpoint(
    file: UploadFile = File(...),
    podcast_mode: bool = Form(True),
    dialogue_mode: bool = Form(False),
    voice_a: str = Form(DEFAULT_VOICE_ID),
    voice_b: str = Form("en-US-AvaMultilingualNeural"),
) -> ExtractResponse:
    """Ingests uploaded document (PDF, Word docx, TXT, MD) and converts into podcast or 2-person dialogue."""
    from app.extract.document import extract_document
    from app.podcast.cadence import shape_article_into_podcast
    from app.podcast.dialogue import shape_article_into_dialogue

    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    title, paragraphs = extract_document(file.filename or "Uploaded Document", file_bytes)
    if not paragraphs:
        raise HTTPException(status_code=422, detail="No readable text paragraphs found in document.")

    file_hash = hashlib.sha256(file_bytes[:1024]).hexdigest()[:10]
    safe_name = re.sub(r"[^a-zA-Z0-9_\-\.]", "_", file.filename or "doc")
    doc_url = f"file://uploaded/{safe_name}-{file_hash}"

    if dialogue_mode:
        podcast_sents = shape_article_into_dialogue(
            title, paragraphs, voice_a=voice_a, voice_b=voice_b
        )
        extractor_label = "dialogue_document"
    elif podcast_mode:
        podcast_sents = shape_article_into_podcast(title, paragraphs)
        extractor_label = "podcast_document"
    else:
        from app.text import create_processed_article
        markdown_body = "\n\n".join(paragraphs)
        processed = create_processed_article(
            url=doc_url,
            title=title,
            markdown=markdown_body,
            extractor_used="uploaded_document",
        )
        podcast_sents = [s.to_dict() for s in processed.sentences]
        extractor_label = "uploaded_document"

    word_count = sum(len(p.split()) for p in paragraphs)
    est_minutes = max(0.5, round(word_count / 155.0, 1))

    import json
    sentences_payload = json.dumps(podcast_sents)
    try:
        DB.save_article({
            "url": doc_url,
            "title": title,
            "author": "Focus Dialogue" if dialogue_mode else "Document Import",
            "sitename": file.filename or "Uploaded File",
            "date": None,
            "extractor_used": extractor_label,
            "word_count": word_count,
            "estimated_read_minutes": est_minutes,
            "sentences_json": sentences_payload,
        })
    except Exception as exc:
        logger.warning("Could not persist uploaded file to DB: %s", exc)

    return ExtractResponse(
        url=doc_url,
        title=title,
        author="Focus Dialogue" if dialogue_mode else "Document Import",
        sitename=file.filename or "Uploaded File",
        date=None,
        extractor_used=extractor_label,
        word_count=word_count,
        estimated_read_minutes=est_minutes,
        sentences=[SentenceModel(**s) for s in podcast_sents],
    )


@app.get("/api/tts")
async def stream_tts(
    text: str = Query(..., min_length=1, max_length=600, description="Sentence to speak"),
    voice: str = Query(DEFAULT_VOICE_ID, description="Neural Voice ID"),
    rate: str = Query("+0%", description="Speaking speed adjustment (e.g. +0%, +20%)"),
    engine: str = Query("edge", description="TTS Engine (edge | kokoro)"),
) -> StreamingResponse:
    """Synthesizes or retrieves cached MP3 audio bytes for a single sentence."""
    try:
        audio_bytes, was_hit = await get_or_synthesize_speech(
            text=text, voice=voice, rate=rate, engine=engine
        )
    except Exception as exc:
        logger.error("TTS synthesis error: %s", exc)
        raise HTTPException(status_code=503, detail=f"TTS synthesis failed: {exc}") from exc

    return StreamingResponse(
        io.BytesIO(audio_bytes),
        media_type="audio/mpeg",
        headers={
            "X-Cache": "HIT" if was_hit else "MISS",
            "Cache-Control": "public, max-age=3600",
        },
    )


@app.post("/api/feedback")
async def submit_feedback(request: FeedbackRequest):
    """Stores user ratings and issue reports."""
    from app.feedback import save_feedback
    entry = save_feedback(request)
    return {"status": "ok", "message": "Feedback received. Thank you!", "feedback": entry}


@app.get("/api/feedback")
async def list_feedback(limit: int = 50):
    """Retrieves recent user feedback entries."""
    from app.feedback import get_recent_feedback
    return {"feedback": get_recent_feedback(limit=limit)}


@app.post("/api/progress")
async def update_progress(req: ProgressRequest):
    """Updates user reading progress for an article."""
    progress = DB.update_progress(
        url=req.url,
        current_sentence_idx=req.current_sentence_idx,
        total_sentences=req.total_sentences,
    )
    return {"status": "ok", "progress": progress}


@app.get("/api/history")
async def get_history(limit: int = Query(20, ge=1, le=100)):
    """Retrieves recently read articles with progress."""
    history = DB.get_reading_history(limit=limit)
    return {"history": history}


# Static assets & Reader UI

STATIC_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.api_route("/", methods=["GET", "HEAD"])
async def serve_index() -> FileResponse:
    """Serves the single-page reader and lookahead audio player UI."""
    index_file = STATIC_DIR / "index.html"
    if not index_file.exists():
        raise HTTPException(status_code=404, detail="UI index.html not found.")
    return FileResponse(
        index_file,
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )

