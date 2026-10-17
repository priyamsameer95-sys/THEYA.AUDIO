"""theya.voice Backend RAG Pipeline & 3-Eval Quality Suite."""
from __future__ import annotations

from app.rag.evals import (
    eval_anti_slop_dialogue_quality,
    eval_context_relevance_and_recall,
    eval_faithfulness_and_grounding,
    get_eval_dashboard_summary,
    run_backend_eval_suite,
)
from app.rag.pipeline import (
    distill_document_ideas,
    index_document_for_rag,
    query_rag,
    retrieve_top_chunks,
)

__all__ = [
    "distill_document_ideas",
    "eval_anti_slop_dialogue_quality",
    "eval_context_relevance_and_recall",
    "eval_faithfulness_and_grounding",
    "get_eval_dashboard_summary",
    "index_document_for_rag",
    "query_rag",
    "retrieve_top_chunks",
    "run_backend_eval_suite",
]
