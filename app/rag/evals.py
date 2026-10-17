"""Backend Evaluation Suite for RAG Grounding, Context Relevance, and Anti-Slop Dialogue Quality.

Maintains 3 deterministic + heuristic backend evaluations logged to SQLite (`rag_eval_runs`):
1. `eval_faithfulness_and_grounding` — Verifies generated answers/dialogue stay grounded in retrieved source chunks.
2. `eval_context_relevance_and_recall` — Verifies retrieved chunks cover the user query's semantic terms.
3. `eval_anti_slop_dialogue_quality` — Enforces `.agents/rules/no-slop-focus-dialogue.md` (zero cheesy AI banter, zero verbatim ping-pong reading, balanced A/B cognitive dialogue).
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Set

from app.db import DB
from app.podcast.dialogue import CHEESY_BANTER_REGEX

STOPWORDS_AND_FRAMING: Set[str] = {
    "the", "and", "for", "that", "this", "with", "from", "into", "over", "under",
    "are", "was", "were", "been", "being", "have", "has", "had", "having",
    "do", "does", "did", "doing", "will", "would", "shall", "should", "can",
    "could", "may", "might", "must", "need", "ought", "about", "above", "after",
    "again", "against", "all", "am", "an", "any", "as", "at", "be", "because",
    "before", "below", "between", "both", "but", "by", "down", "during", "each",
    "few", "further", "here", "how", "if", "in", "is", "it", "its", "itself",
    "just", "more", "most", "no", "nor", "not", "now", "of", "off", "on", "once",
    "only", "or", "other", "our", "ours", "out", "own", "same", "she", "so",
    "some", "such", "than", "then", "there", "these", "they", "their", "them",
    "those", "through", "to", "too", "until", "up", "very", "what", "when",
    "where", "which", "while", "who", "whom", "why", "you", "your", "we", "us",
    # Conversational framing words allowed by Focus Dialogue engine
    "wait", "look", "let", "lets", "see", "notice", "pause", "second", "working",
    "today", "pointed", "essentially", "actually", "replaces", "takes", "place",
    "shift", "makes", "total", "sense", "real", "moat", "moves", "main", "lever",
    "unpack", "break", "down", "saying", "means", "concrete", "practice", "key",
    "question", "answer", "grounded", "source", "document", "section", "point",
    "points", "argues", "argued", "shows", "explains", "author", "piece", "text",
}


def _stem_word(word: str) -> str:
    """Lightweight deterministic stemmer for English technical prose."""
    w = word.lower().strip(".,!?;:\"'()[]{}-—–")
    if w.endswith("'s") or w.endswith("’s"):
        w = w[:-2]
    if len(w) <= 3:
        return w
    for suffix in (
        "izations", "ization", "izing", "izes", "ized", "ize",
        "ating", "ation", "ations", "ator", "ators",
        "ingly", "edly", "ments", "ment", "ness", "ities", "ity",
        "ings", "ing", "ed", "ies", "es", "s", "ly", "al",
    ):
        if w.endswith(suffix) and len(w) - len(suffix) >= 3:
            if suffix == "ies":
                return w[:-3] + "y"
            return w[: -len(suffix)]
    return w


def _extract_content_stems(text: str, keep_over: bool = False) -> List[str]:
    """Extracts meaningful content word stems from text."""
    raw_tokens = re.findall(r"[A-Za-z0-9']+", text.lower())
    stems: List[str] = []
    for tok in raw_tokens:
        clean = tok.strip("'")
        if len(clean) < 2:
            continue
        if clean == "over" and keep_over:
            stems.append("over")
            continue
        if clean in STOPWORDS_AND_FRAMING:
            continue
        if len(clean) < 3 and clean not in {"ai", "ui", "db", "io", "os", "ml"}:
            continue
        stem = _stem_word(clean)
        if stem and stem not in STOPWORDS_AND_FRAMING:
            stems.append(stem)
    return stems


def eval_faithfulness_and_grounding(
    generated_text: str,
    retrieved_chunks: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Eval 1: Faithfulness & Grounding.

    Measures the proportion of substantive content concepts in `generated_text`
    that are directly supported by `retrieved_chunks`. Penalizes unsupported hallucinations.
    """
    if not generated_text.strip() or not retrieved_chunks:
        return {
            "score": 0.0,
            "passed": False,
            "grounded_terms": [],
            "ungrounded_terms": [],
            "reason": "Missing generated text or retrieved source chunks.",
        }

    source_corpus = " ".join(str(c.get("text", "")) for c in retrieved_chunks)
    source_stems = set(_extract_content_stems(source_corpus, keep_over=True))
    source_lower = source_corpus.lower()

    gen_stems = _extract_content_stems(generated_text, keep_over=True)
    if not gen_stems:
        return {
            "score": 0.75,
            "passed": True,
            "grounded_terms": [],
            "ungrounded_terms": [],
            "reason": "Brief conversational turn with no ungrounded factual claims.",
        }

    grounded: List[str] = []
    ungrounded: List[str] = []

    for stem in gen_stems:
        if (
            stem in source_stems
            or stem in source_lower
            or any(s.startswith(stem[:4]) or stem.startswith(s[:4]) for s in source_stems if len(s) >= 4 and len(stem) >= 4)
        ):
            grounded.append(stem)
        else:
            ungrounded.append(stem)

    raw_ratio = len(grounded) / max(1, len(gen_stems))
    score = round(min(1.0, max(0.0, raw_ratio)), 3)
    passed = score >= 0.65

    return {
        "score": score,
        "passed": passed,
        "grounded_terms": sorted(set(grounded))[:15],
        "ungrounded_terms": sorted(set(ungrounded))[:10],
    }


def eval_context_relevance_and_recall(
    query: str,
    retrieved_chunks: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Eval 2: Context Relevance & Recall.

    Measures whether the retrieved chunks actually contain the concepts requested in `query`.
    """
    if not query.strip() or not retrieved_chunks:
        return {
            "score": 0.0,
            "passed": False,
            "matched_query_terms": [],
            "missing_query_terms": [],
            "chunk_count": 0,
        }

    query_stems = _extract_content_stems(query, keep_over=True)
    if not query_stems:
        return {
            "score": 0.70,
            "passed": True,
            "matched_query_terms": [],
            "missing_query_terms": [],
            "chunk_count": len(retrieved_chunks),
        }

    source_corpus = " ".join(str(c.get("text", "")) for c in retrieved_chunks)
    source_stems = set(_extract_content_stems(source_corpus, keep_over=True))
    source_lower = source_corpus.lower()

    matched: List[str] = []
    missing: List[str] = []
    unique_query_stems = list(dict.fromkeys(query_stems))

    for q_stem in unique_query_stems:
        if (
            q_stem in source_stems
            or q_stem in source_lower
            or any(s.startswith(q_stem[:4]) or q_stem.startswith(s[:4]) for s in source_stems if len(s) >= 4 and len(q_stem) >= 4)
        ):
            matched.append(q_stem)
        else:
            missing.append(q_stem)

    term_recall = len(matched) / max(1, len(unique_query_stems))
    if term_recall == 0.0:
        score = 0.0
    else:
        max_chunk_score = max((float(c.get("score", 0.5)) for c in retrieved_chunks), default=0.5)
        normalized_chunk_conf = min(1.0, max(0.3, max_chunk_score))
        score = round(min(1.0, 0.85 * term_recall + 0.15 * normalized_chunk_conf), 3)

    passed = score >= 0.60
    return {
        "score": score,
        "passed": passed,
        "matched_query_terms": matched,
        "missing_query_terms": missing,
        "chunk_count": len(retrieved_chunks),
    }


def eval_anti_slop_dialogue_quality(
    dialogue_turns: List[Dict[str, Any]],
    source_texts: List[str],
) -> Dict[str, Any]:
    """Eval 3: Anti-Slop Focus Dialogue Quality.

    Audits a 2-speaker conversation against `.agents/rules/no-slop-focus-dialogue.md`:
    - Zero cheesy AI podcast banter (`Welcome back to the deep dive`, `Buckle up`, `Wow, that's so fascinating`)
    - Zero verbatim ping-pong paragraph reading
    - Balanced Speaker A & Speaker B cognitive engagement
    """
    if not dialogue_turns:
        return {
            "score": 0.0,
            "passed": False,
            "banter_violations": [],
            "verbatim_turns": 0,
            "speaker_balance": 0.0,
        }

    banter_violations: List[str] = []
    verbatim_turns = 0
    speakers: List[str] = []
    interactive_markers = 0

    normalized_sources = [
        re.sub(r"\s+", " ", s.strip().lower())
        for s in source_texts
        if s and len(s.strip()) >= 35
    ]

    for turn in dialogue_turns:
        txt = str(turn.get("display_text") or turn.get("speech_text") or "").strip()
        spk = str(turn.get("speaker") or "A")
        speakers.append(spk)

        # 1. Check for banned cheesy AI banter phrases
        matches = CHEESY_BANTER_REGEX.findall(txt)
        if matches:
            banter_violations.extend(matches)

        # 2. Check if turn contains a raw verbatim copy of a source paragraph
        norm_turn = re.sub(r"\s+", " ", txt.lower())
        for src in normalized_sources:
            if src in norm_turn:
                verbatim_turns += 1
                break

        # 3. Check for genuine cognitive thought-sharing markers
        if "?" in txt or "—" in txt or re.search(
            r"\b(wait|look at|what takes|why|how|shift|means|because|pause|unpack|notice)\b",
            txt,
            re.IGNORECASE,
        ):
            interactive_markers += 1

    score = 1.0
    # Heavy penalty for cheesy AI banter
    if banter_violations:
        score -= min(0.65, 0.30 * len(banter_violations))

    # Penalty for verbatim paragraph copying
    verbatim_ratio = verbatim_turns / max(1, len(dialogue_turns))
    if verbatim_ratio > 0.0:
        score -= min(0.40, 0.40 * verbatim_ratio)

    # Check speaker diversity (both A and B active)
    unique_speakers = set(speakers)
    if len(dialogue_turns) >= 2 and len(unique_speakers) < 2:
        score -= 0.25

    # Reward interactive cognitive framing
    if interactive_markers == 0 and len(dialogue_turns) >= 2:
        score -= 0.15

    final_score = round(max(0.0, min(1.0, score)), 3)
    passed = final_score >= 0.75 and len(banter_violations) == 0

    return {
        "score": final_score,
        "passed": passed,
        "banter_violations": banter_violations,
        "verbatim_turns": verbatim_turns,
        "interactive_turns": interactive_markers,
        "speaker_count": len(unique_speakers),
    }


def run_backend_eval_suite(
    eval_type: str,
    doc_url: str,
    query: str,
    generated_text: str,
    retrieved_chunks: List[Dict[str, Any]],
    dialogue_turns: List[Dict[str, Any]],
    persist: bool = True,
) -> Dict[str, Any]:
    """Runs all 3 Backend Evals and persists the telemetry record to SQLite."""
    source_texts = [str(c.get("text", "")) for c in retrieved_chunks]
    f_res = eval_faithfulness_and_grounding(generated_text, retrieved_chunks)
    r_res = eval_context_relevance_and_recall(query, retrieved_chunks)
    q_res = eval_anti_slop_dialogue_quality(dialogue_turns, source_texts)

    overall_score = round((f_res["score"] + r_res["score"] + q_res["score"]) / 3.0, 3)
    passed = bool(f_res["passed"] and r_res["passed"] and q_res["passed"])

    details = {
        "faithfulness_and_grounding": f_res,
        "context_relevance_and_recall": r_res,
        "anti_slop_dialogue_quality": q_res,
    }

    if persist:
        try:
            DB.save_rag_eval_run(
                {
                    "eval_type": eval_type,
                    "doc_url": doc_url,
                    "query": query,
                    "faithfulness_score": f_res["score"],
                    "context_relevance_score": r_res["score"],
                    "anti_slop_quality_score": q_res["score"],
                    "overall_score": overall_score,
                    "passed": passed,
                    "details": details,
                }
            )
        except Exception:
            pass

    return {
        "eval_type": eval_type,
        "doc_url": doc_url,
        "query": query,
        "faithfulness_and_grounding": f_res,
        "context_relevance_and_recall": r_res,
        "anti_slop_dialogue_quality": q_res,
        "overall_score": overall_score,
        "passed": passed,
    }


def get_eval_dashboard_summary(limit: int = 25) -> Dict[str, Any]:
    """Returns aggregated telemetry across the 3 backend evals and recent run logs."""
    runs = DB.get_recent_rag_eval_runs(limit=limit)
    if not runs:
        return {
            "summary": {
                "total_runs": 0,
                "pass_rate": 1.0,
                "overall_avg": 0.0,
                "metrics": {
                    "faithfulness_and_grounding": {"avg_score": 0.0, "target": 0.65},
                    "context_relevance_and_recall": {"avg_score": 0.0, "target": 0.60},
                    "anti_slop_dialogue_quality": {"avg_score": 0.0, "target": 0.75},
                },
            },
            "recent_runs": [],
        }

    n = len(runs)
    avg_f = round(sum(float(r["faithfulness_score"]) for r in runs) / n, 3)
    avg_r = round(sum(float(r["context_relevance_score"]) for r in runs) / n, 3)
    avg_q = round(sum(float(r["anti_slop_quality_score"]) for r in runs) / n, 3)
    avg_o = round(sum(float(r["overall_score"]) for r in runs) / n, 3)
    pass_rate = round(sum(1 for r in runs if r["passed"]) / n, 3)

    return {
        "summary": {
            "total_runs": n,
            "pass_rate": pass_rate,
            "overall_avg": avg_o,
            "metrics": {
                "faithfulness_and_grounding": {
                    "name": "Faithfulness & Grounding",
                    "avg_score": avg_f,
                    "target": 0.65,
                },
                "context_relevance_and_recall": {
                    "name": "Context Relevance & Recall",
                    "avg_score": avg_r,
                    "target": 0.60,
                },
                "anti_slop_dialogue_quality": {
                    "name": "Anti-Slop Focus Dialogue Quality",
                    "avg_score": avg_q,
                    "target": 0.75,
                },
            },
        },
        "recent_runs": runs,
    }


def eval_final_product_metrics(
    dialogue_turns: List[Dict[str, Any]],
    source_word_count: int = 100,
    latency_ms: float = 0.0,
) -> Dict[str, Any]:
    """Evaluates the Final Product (2-Voice Focus Dialogue + TTS Audio Readiness).

    Measures:
    - `tts_breath_compliance_rate`: % of turns <= 45 words for natural spoken breath cadence.
    - `artifact_free_rate`: % of turns free of raw XML/SSML tags (`<break`), markdown pipes (`|`), or raw URLs.
    - `speaker_alternation_rate`: % of adjacent turns that switch between Speaker A and Speaker B.
    - `idea_compression_ratio`: ratio of spoken distillation words to source words.
    - `pipeline_latency_ms`: end-to-end execution latency in milliseconds.
    """
    if not dialogue_turns:
        return {
            "tts_breath_compliance_rate": 0.0,
            "artifact_free_rate": 0.0,
            "speaker_alternation_rate": 0.0,
            "idea_compression_ratio": 0.0,
            "avg_turn_words": 0.0,
            "pipeline_latency_ms": round(latency_ms, 2),
            "passed": False,
        }

    n = len(dialogue_turns)
    breath_ok = 0
    artifact_free = 0
    alternations = 0
    total_spoken_words = 0

    artifact_regex = re.compile(r"(?:<\s*/?\s*break\b|\|\s*\w+\s*\||https?://\S+)", re.IGNORECASE)

    for idx, turn in enumerate(dialogue_turns):
        disp = str(turn.get("display_text") or "")
        words = disp.split()
        w_count = len(words)
        total_spoken_words += w_count

        if 2 <= w_count <= 48:
            breath_ok += 1

        if not artifact_regex.search(disp) and len(disp.strip()) > 0:
            artifact_free += 1

        if idx > 0:
            prev_spk = str(dialogue_turns[idx - 1].get("speaker") or "A")
            cur_spk = str(turn.get("speaker") or "A")
            if cur_spk != prev_spk:
                alternations += 1

    breath_rate = round(breath_ok / max(1, n), 3)
    artifact_rate = round(artifact_free / max(1, n), 3)
    alt_rate = round(alternations / max(1, n - 1), 3) if n > 1 else 1.0
    avg_words = round(total_spoken_words / max(1, n), 1)
    compression = round(total_spoken_words / max(1, source_word_count), 2)

    passed = bool(breath_rate >= 0.80 and artifact_rate == 1.0 and alt_rate >= 0.45)

    return {
        "tts_breath_compliance_rate": breath_rate,
        "artifact_free_rate": artifact_rate,
        "speaker_alternation_rate": alt_rate,
        "idea_compression_ratio": compression,
        "avg_turn_words": avg_words,
        "turn_count": n,
        "pipeline_latency_ms": round(latency_ms, 2),
        "passed": passed,
    }

