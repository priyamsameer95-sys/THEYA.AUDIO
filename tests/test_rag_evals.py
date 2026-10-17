"""Unit and integration tests for the Backend RAG Pipeline and 3-Eval Quality Suite."""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app
from app.rag.evals import (
     eval_anti_slop_dialogue_quality,
    eval_context_relevance_and_recall,
    eval_faithfulness_and_grounding,
    run_backend_eval_suite,
)
from app.rag.pipeline import index_document_for_rag, query_rag, retrieve_top_chunks


def test_rag_chunking_and_hybrid_retrieval() -> None:
    """Verifies RAG chunking and hybrid BM25 + TF-IDF cosine retrieval accuracy."""
    doc_url = "https://example.com/consensus-architecture"
    title = "Consensus & Memory Systems"
    paragraphs = [
        "Working memory in human learners saturates rapidly when presented with unbroken monotone text streams exceeding forty seconds.",
        "Byzantine fault tolerance requires distributed nodes to reach consensus even when malicious actors broadcast conflicting state transitions.",
        "However, the primary scaling bottleneck in classical PBFT is the quadratic O(n^2) message complexity required during each voting round.",
        "Acoustic brown noise filters mask high-frequency transient distractions in open studio environments.",
    ]

    chunks = index_document_for_rag(doc_url=doc_url, title=title, paragraphs=paragraphs, chunk_size_words=45)
    assert len(chunks) >= 2

    top_hits = retrieve_top_chunks(
        query="What is the scaling bottleneck in Byzantine fault tolerance voting rounds?",
        doc_url=doc_url,
        top_k=2,
    )
    assert len(top_hits) >= 1
    top_text = " ".join(c["text"].lower() for c in top_hits)
    assert "quadratic" in top_text or "byzantine" in top_text
    assert top_hits[0]["score"] > 0.0


def test_three_backend_evals_discriminate_good_vs_bad() -> None:
    """Verifies all 3 backend evals accurately score grounded/anti-slop output vs hallucinated/slop output."""
    source_chunks = [
        {
            "chunk_id": "c0",
            "text": "Linear's CEO argued that the era of growth hacking is over and product teams must focus on craft and quality.",
            "score": 0.88,
        },
        {
            "chunk_id": "c1",
            "text": "As AI commoditizes underlying models, companies differentiate through network effects, brand, and product taste.",
            "score": 0.79,
        },
    ]
    query = "Why is growth hacking over and how do AI companies differentiate?"

    # 1. Eval 1: Faithfulness & Grounding
    good_answer = (
        "Growth hacking is over because teams now must focus on product craft and quality, "
        "differentiating through network effects and brand as AI models commoditize."
    )
    hallucinated_answer = (
        "Submarine nuclear reactors on Europa require titanium valves and orbital laser telemetry."
    )

    faith_good = eval_faithfulness_and_grounding(good_answer, source_chunks)
    faith_bad = eval_faithfulness_and_grounding(hallucinated_answer, source_chunks)
    assert faith_good["score"] >= 0.65
    assert faith_good["passed"] is True
    assert faith_bad["score"] < 0.35
    assert faith_bad["passed"] is False

    # 2. Eval 2: Context Relevance & Recall
    rel_good = eval_context_relevance_and_recall(query, source_chunks)
    rel_bad = eval_context_relevance_and_recall(
        "How do medieval catapults siege castles?", source_chunks
    )
    assert rel_good["score"] >= 0.60
    assert rel_good["passed"] is True
    assert rel_bad["score"] < 0.40
    assert rel_bad["passed"] is False

    # 3. Eval 3: Anti-Slop Dialogue Quality (No Banter, No Verbatim Ping-Pong, Balanced Turns)
    good_dialogue = [
        {
            "speaker": "A",
            "display_text": "We're working through Product Taste today, and look at what Linear's CEO pointed out — the era of growth hacking is essentially over.",
        },
        {
            "speaker": "B",
            "display_text": "Wait — if growth hacking is over, what actually replaces it as the main lever for product teams?",
        },
        {
            "speaker": "A",
            "display_text": "What takes its place is a focus on craft and quality, especially as AI commoditizes proprietary models.",
        },
        {
            "speaker": "B",
            "display_text": "See, that shift makes total sense — the real moat moves to network effects and brand.",
        },
    ]
    slop_dialogue = [
        {
            "speaker": "A",
            "display_text": "Welcome back to the deep dive! Buckle up! Linear's CEO argued that the era of growth hacking is over and product teams must focus on craft and quality.",
        },
        {
            "speaker": "B",
            "display_text": "Wow, that's so fascinating! That's a great point! As AI commoditizes underlying models, companies differentiate through network effects, brand, and product taste.",
        },
    ]

    qual_good = eval_anti_slop_dialogue_quality(good_dialogue, [c["text"] for c in source_chunks])
    qual_slop = eval_anti_slop_dialogue_quality(slop_dialogue, [c["text"] for c in source_chunks])
    assert qual_good["score"] >= 0.75
    assert qual_good["passed"] is True
    assert qual_slop["score"] < 0.55
    assert qual_slop["passed"] is False


def test_rag_api_query_and_eval_endpoints() -> None:
    """Verifies /api/extract/text indexes into RAG, runs the 3 backend evals, and serves /api/rag/query and /api/rag/evals."""
    client = TestClient(app)
    text = (
        "# Architecture of Focus\n\n"
        "Cognitive overload happens when dense technical clauses stack without a moment to synthesize.\n\n"
        "In his eyes, the era of passive wall-of-text reading was over - and in its place was an active two-voice working session where learners challenge assumptions.\n\n"
        "Consequently, retention improves when a Focus Partner interrupts monotone delivery rather than reading verbatim paragraphs."
    )
    res_ext = client.post(
        "/api/extract/text",
        json={
            "text": text,
            "title": "Architecture of Focus",
            "podcast_mode": True,
            "dialogue_mode": True,
        },
    )
    assert res_ext.status_code == 200
    doc_data = res_ext.json()
    doc_url = doc_data["url"]

    # Query RAG endpoint against the extracted document
    res_rag = client.post(
        "/api/rag/query",
        json={
            "query": "Why does retention improve and what replaces passive reading?",
            "doc_url": doc_url,
            "top_k": 3,
        },
    )
    assert res_rag.status_code == 200
    rag_payload = res_rag.json()
    assert "answer" in rag_payload
    assert "dialogue_turns" in rag_payload
    assert len(rag_payload["dialogue_turns"]) >= 2
    assert len(rag_payload["retrieved_chunks"]) >= 1
    assert "evals" in rag_payload
    evals = rag_payload["evals"]
    assert "faithfulness_and_grounding" in evals
    assert "context_relevance_and_recall" in evals
    assert "anti_slop_dialogue_quality" in evals
    assert evals["overall_score"] > 0.5

    # Inspect persisted backend evals dashboard endpoint
    res_evals = client.get("/api/rag/evals")
    assert res_evals.status_code == 200
    evals_history = res_evals.json()
    assert "summary" in evals_history
    assert "recent_runs" in evals_history
    assert len(evals_history["recent_runs"]) >= 1
    metrics = evals_history["summary"]["metrics"]
    assert "faithfulness_and_grounding" in metrics
    assert "context_relevance_and_recall" in metrics
    assert "anti_slop_dialogue_quality" in metrics
