"""Backend RAG (Retrieval-Augmented Generation) Pipeline for they.audio.

Provides:
1. Semantic-boundary paragraph & sliding-window chunking (`index_document_for_rag`).
2. Hybrid BM25 + TF-IDF Cosine + Bigram Overlap Retrieval (`retrieve_top_chunks`).
3. Grounded 2-Voice Focus Dialogue synthesis + automatic 3-Eval verification (`query_rag`).
"""
from __future__ import annotations

import hashlib
import math
import re
from collections import Counter
from typing import Any, Dict, List, Optional

from app.db import DB
from app.podcast.dialogue import (
    _reframe_written_to_spoken as _rewrite_for_spoken_clarity,
    shape_article_into_dialogue,
)
from app.rag.evals import _extract_content_stems, run_backend_eval_suite

DEFAULT_VOICE_A = "en-US-AndrewMultilingualNeural"
DEFAULT_VOICE_B = "en-US-AvaMultilingualNeural"


def index_document_for_rag(
    doc_url: str,
    title: str,
    paragraphs: List[str],
    chunk_size_words: int = 85,
    overlap_words: int = 15,
) -> List[Dict[str, Any]]:
    """Splits document paragraphs into overlapping semantic chunks and indexes them into SQLite."""
    clean_paras = [p.strip() for p in paragraphs if p and p.strip()]
    if not clean_paras:
        return []

    raw_chunks: List[str] = []
    current_words: List[str] = []

    for para in clean_paras:
        p_words = para.split()
        # Keep individual distinct paragraphs separate if chunk_size_words is small or paragraph is self-contained
        if len(p_words) <= chunk_size_words and len(clean_paras) <= 8:
            if current_words:
                raw_chunks.append(" ".join(current_words))
                current_words = []
            raw_chunks.append(para)
            continue

        if len(current_words) + len(p_words) <= chunk_size_words:
            current_words.extend(p_words)
        else:
            if current_words:
                raw_chunks.append(" ".join(current_words))
                overlap = current_words[-overlap_words:] if overlap_words > 0 else []
                current_words = list(overlap) + p_words
            else:
                # Paragraph itself exceeds chunk_size_words; slice with overlap
                step = max(15, chunk_size_words - overlap_words)
                for i in range(0, len(p_words), step):
                    slice_words = p_words[i : i + chunk_size_words]
                    if slice_words:
                        raw_chunks.append(" ".join(slice_words))

    if current_words:
        raw_chunks.append(" ".join(current_words))

    url_hash = hashlib.sha256(doc_url.encode()).hexdigest()[:10]
    chunks: List[Dict[str, Any]] = []
    for idx, text in enumerate(raw_chunks):
        stems = _extract_content_stems(text, keep_over=True)
        chunks.append(
            {
                "chunk_id": f"{url_hash}_c{idx}",
                "doc_url": doc_url,
                "title": title,
                "chunk_idx": idx,
                "text": text,
                "token_count": len(text.split()),
                "keywords": stems,
                "tokens": stems,
            }
        )

    DB.save_rag_chunks(doc_url, chunks)
    return chunks


def _compute_hybrid_scores(
    query: str,
    chunks: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Scores candidate chunks using Hybrid BM25 + TF-IDF Cosine + Bigram phrase boost."""
    if not chunks:
        return []

    query_stems = _extract_content_stems(query, keep_over=True)
    if not query_stems:
        query_stems = re.findall(r"[a-z0-9]+", query.lower())

    n_docs = len(chunks)
    doc_tokens_list: List[List[str]] = []
    df_counter: Counter[str] = Counter()

    for ch in chunks:
        toks = ch.get("tokens") or ch.get("keywords")
        if not isinstance(toks, list) or not toks:
            toks = _extract_content_stems(str(ch.get("text", "")), keep_over=True)
        doc_tokens_list.append(toks)
        for unique_t in set(toks):
            df_counter[unique_t] += 1

    avgdl = sum(len(t) for t in doc_tokens_list) / max(1, n_docs)
    k1 = 1.5
    b = 0.75

    q_counts = Counter(query_stems)
    q_bigrams = {
        f"{query_stems[i]} {query_stems[i+1]}"
        for i in range(len(query_stems) - 1)
    }

    scored_chunks: List[Dict[str, Any]] = []
    for ch, d_toks in zip(chunks, doc_tokens_list):
        d_counts = Counter(d_toks)
        dl = max(1, len(d_toks))

        # 1. BM25 score
        bm25 = 0.0
        for q_term in set(query_stems):
            tf = d_counts.get(q_term, 0)
            # Prefix / root fallback for technical variants
            if tf == 0 and len(q_term) >= 4:
                tf = sum(
                    cnt
                    for dt, cnt in d_counts.items()
                    if len(dt) >= 4 and (dt.startswith(q_term[:4]) or q_term.startswith(dt[:4]))
                )
            if tf <= 0:
                continue
            df = df_counter.get(q_term, 1)
            idf = math.log(1.0 + (n_docs - df + 0.5) / (df + 0.5))
            denom = tf + k1 * (1.0 - b + b * (dl / max(1.0, avgdl)))
            bm25 += idf * ((tf * (k1 + 1.0)) / denom)

        # 2. TF-IDF Cosine Similarity
        dot = 0.0
        q_norm = 0.0
        d_norm = 0.0
        all_terms = set(q_counts.keys()) | set(d_counts.keys())
        for term in all_terms:
            df = df_counter.get(term, 1)
            idf = 1.0 + math.log((n_docs + 1.0) / (df + 1.0))
            qw = q_counts.get(term, 0) * idf
            dw = d_counts.get(term, 0) * idf
            dot += qw * dw
            q_norm += qw * qw
            d_norm += dw * dw
        cosine = dot / (math.sqrt(q_norm) * math.sqrt(d_norm)) if (q_norm > 0 and d_norm > 0) else 0.0

        # 3. Bigram overlap boost
        d_bigrams = {
            f"{d_toks[i]} {d_toks[i+1]}"
            for i in range(len(d_toks) - 1)
        }
        bigram_hits = len(q_bigrams & d_bigrams)
        bigram_boost = min(0.25, 0.12 * bigram_hits)

        # Normalize hybrid score into [0.0, 1.0]
        norm_bm25 = 1.0 - math.exp(-0.55 * bm25) if bm25 > 0 else 0.0
        hybrid_score = round(min(1.0, 0.55 * norm_bm25 + 0.35 * cosine + bigram_boost), 4)

        enriched = dict(ch)
        enriched["score"] = hybrid_score
        scored_chunks.append(enriched)

    scored_chunks.sort(key=lambda x: float(x.get("score", 0.0)), reverse=True)
    return scored_chunks


def retrieve_top_chunks(
    query: str,
    doc_url: Optional[str] = None,
    top_k: int = 3,
) -> List[Dict[str, Any]]:
    """Retrieves the top-K most relevant chunks from SQLite using Hybrid BM25 + TF-IDF Cosine."""
    candidates = DB.get_rag_chunks(doc_url=doc_url)
    if not candidates and doc_url:
        # Fallback: if article exists in DB.articles but wasn't indexed yet, index on-the-fly
        article = DB.get_article(doc_url)
        if article:
            import json
            sents = json.loads(article.get("sentences_json", "[]"))
            paras = [s.get("display_text", "") for s in sents if s.get("display_text")]
            candidates = index_document_for_rag(
                doc_url=doc_url,
                title=article.get("title", "Document"),
                paragraphs=paras,
            )

    scored = _compute_hybrid_scores(query, candidates)
    return scored[: max(1, top_k)]


def _synthesize_grounded_rag_response(
    query: str,
    title: str,
    top_chunks: List[Dict[str, Any]],
    voice_a: str = DEFAULT_VOICE_A,
    voice_b: str = DEFAULT_VOICE_B,
) -> Dict[str, Any]:
    """Synthesizes a grounded answer and 2-person Focus Dialogue directly from retrieved chunks."""
    if not top_chunks:
        return {
            "answer": "No relevant context chunks were found in the indexed document.",
            "dialogue_turns": [],
        }

    # Build a grounded synthesis from the top retrieved chunks
    primary_texts = [_rewrite_for_spoken_clarity(str(c.get("text", ""))) for c in top_chunks[:2]]
    grounded_answer = " ".join(primary_texts)

    # Shape retrieved context into an authentic 2-person Focus Dialogue working session
    chunk_paragraphs = [str(c.get("text", "")) for c in top_chunks if c.get("text")]
    raw_turns = shape_article_into_dialogue(
        title=title,
        paragraphs=chunk_paragraphs,
        voice_a=voice_a,
        voice_b=voice_b,
    )

    # Replace the generic intro turn with a direct focus question anchored in the user's query
    clean_q = query.strip().rstrip("?") + "?"
    focused_turns: List[Dict[str, Any]] = [
        {
            "idx": 0,
            "display_text": f"Wait — let's look closely at this question: {clean_q}",
            "speech_text": f"Wait, let's look closely at this question: {clean_q}",
            "kind": "prose",
            "pause_after_ms": 380,
            "mood": "question",
            "speaker": "B",
            "speaker_name": "Focus Partner",
            "voice_id": voice_b,
        }
    ]

    for turn in raw_turns[1:]:
        updated = dict(turn)
        updated["idx"] = len(focused_turns)
        focused_turns.append(updated)

    # Ensure at least 2 balanced turns
    if len(focused_turns) < 2 and primary_texts:
        focused_turns.append(
            {
                "idx": 1,
                "display_text": f"What the source text shows is this: {primary_texts[0]}",
                "speech_text": f"What the source text shows is this: {primary_texts[0]}",
                "kind": "prose",
                "pause_after_ms": 340,
                "mood": "emphasis",
                "speaker": "A",
                "speaker_name": "Anchor",
                "voice_id": voice_a,
            }
        )

    return {
        "answer": grounded_answer,
        "dialogue_turns": focused_turns,
    }


def query_rag(
    query: str,
    doc_url: Optional[str] = None,
    top_k: int = 3,
    voice_a: str = DEFAULT_VOICE_A,
    voice_b: str = DEFAULT_VOICE_B,
) -> Dict[str, Any]:
    """End-to-end RAG query: retrieves chunks, synthesizes grounded 2-voice answer, and runs 3 backend evals."""
    retrieved = retrieve_top_chunks(query=query, doc_url=doc_url, top_k=top_k)
    title = str(retrieved[0].get("title", "Active Document")) if retrieved else "Active Document"
    resolved_url = doc_url or (str(retrieved[0].get("doc_url", "rag://global")) if retrieved else "rag://global")

    synthesis = _synthesize_grounded_rag_response(
        query=query,
        title=title,
        top_chunks=retrieved,
        voice_a=voice_a,
        voice_b=voice_b,
    )

    eval_report = run_backend_eval_suite(
        eval_type="rag_query",
        doc_url=resolved_url,
        query=query,
        generated_text=synthesis["answer"],
        retrieved_chunks=retrieved,
        dialogue_turns=synthesis["dialogue_turns"],
        persist=True,
    )

    return {
        "query": query,
        "doc_url": resolved_url,
        "title": title,
        "answer": synthesis["answer"],
        "dialogue_turns": synthesis["dialogue_turns"],
        "retrieved_chunks": retrieved,
        "evals": eval_report,
    }
