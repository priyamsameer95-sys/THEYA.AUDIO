"""Two-Person Cognitive Focus Dialogue Engine (Anti-Ping-Pong & Anti-Banter).

Designed specifically for learners who struggle with attention drift or dense text.
Instead of verbatim ping-pong reading or cheesy AI podcast banter, this engine pairs:
- Speaker A (Anchor): Presents the core thesis, mechanisms, and evidence clearly.
- Speaker B (Focus Partner): Interrupts cognitive overload, asks grounding questions,
  highlights pivots, and distills dense clauses into concrete mental models.
"""
from __future__ import annotations

import json
import logging
import os
import re
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

import pysbd

from app.podcast.cadence import analyze_sentence_cadence, sanitize_for_podcast

logger = logging.getLogger("theya.dialogue")

# Hard Rule B: Forbidden Cheesy AI Podcast Banter Patterns
CHEESY_BANTER_PATTERNS: List[str] = [
    r"welcome back to (?:the |our )?deep dive[!.]?",
    r"welcome to (?:the |our )?deep dive[!.]?",
    r"buckle up[!.,]*",
    r"grab your coffee[!.,]*",
    r"wow,?\s+that'?s (?:so )?(?:fascinating|amazing|incredible|wild|crazy)[!.]?",
    r"that'?s a great point[!.]?",
    r"hey everyone,?\s+today we'?re unpacking[^.!?]*[.!?]?",
    r"without further ado,?\s*",
    r"let'?s dive right in[!.]?",
    r"thanks for tuning in[!.]?",
    r"smash that subscribe button[!.]?",
]

CHEESY_BANTER_REGEX = re.compile("|".join(CHEESY_BANTER_PATTERNS), re.IGNORECASE)

# Explicit script speaker prefix detection (if user pastes a pre-formatted dialogue)
SCRIPT_SPEAKER_REGEX = re.compile(
    r"^\s*(?:\*\*)?(Speaker\s*[AB12]|Host(?:\s*[AB12])?|Co-?Host|Anchor|Clarifier|Focus Partner|Q|A)(?:\*\*)?\s*:\s*(.+)$",
    re.IGNORECASE,
)

CONTRAST_START_REGEX = re.compile(
    r"^(?:However|Yet|But|Instead|On the other hand|In contrast|Conversely|Meanwhile),\s*",
    re.IGNORECASE,
)

REVELATION_START_REGEX = re.compile(
    r"^(?:In fact|Crucially|Fundamentally|Remarkably|Importantly|Notice that|The truth is),?\s*",
    re.IGNORECASE,
)


def strip_cheesy_banter(text: str) -> str:
    """Removes banned cheesy AI podcast filler while preserving substantive prose."""
    cleaned = CHEESY_BANTER_REGEX.sub("", text)
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()
    return cleaned


def _extract_focus_concept(sentence: str) -> str:
    """Extracts a concise 2-5 word subject phrase from a sentence for grounded focus prompts."""
    cleaned = re.sub(
        r"^(?:However|Yet|In fact|Crucially|Fundamentally|First|Second|Third|Finally|Therefore|Thus|So),?\s*",
        "",
        sentence.strip(),
        flags=re.IGNORECASE,
    )
    # Take words before the first major verb or punctuation
    clause = re.split(r"[,:;—–]|(?:\b(?:is|are|was|were|requires|causes|means|explains|creates|forces|allows)\b)", cleaned, maxsplit=1)[0]
    words = [w.strip("\"'()[]") for w in clause.split() if w.strip("\"'()[]")]
    if 2 <= len(words) <= 6:
        return " ".join(words).lower()
    if len(words) > 6:
        return " ".join(words[:4]).lower()
    return "this mechanism"


def _distill_dense_sentence(sentence: str) -> Tuple[str, str]:
    """Splits an overloaded multi-clause sentence into (setup_clause, core_takeaway)

    so working memory isn't overwhelmed.
    """
    if " — " in sentence:
        parts = sentence.split(" — ", 1)
        if len(parts[0].split()) >= 5 and len(parts[1].split()) >= 4:
            return parts[0].strip() + ".", parts[1].strip()
    if ": " in sentence and not sentence.lower().startswith("http"):
        parts = sentence.split(": ", 1)
        if len(parts[0].split()) >= 5 and len(parts[1].split()) >= 4:
            return parts[0].strip() + ".", parts[1].strip()
    if ", which " in sentence:
        parts = sentence.split(", which ", 1)
        if len(parts[0].split()) >= 6 and len(parts[1].split()) >= 4:
            return parts[0].strip() + ".", "That directly " + parts[1].strip()
    if " because " in sentence:
        parts = sentence.split(" because ", 1)
        if len(parts[0].split()) >= 6 and len(parts[1].split()) >= 4:
            return parts[0].strip() + ".", "The reason is that " + parts[1].strip()
    return sentence, ""


def _build_turn(
    idx: int,
    raw_text: str,
    speaker: str,
    voice_a: str,
    voice_b: str,
    kind: str = "prose",
    is_paragraph_end: bool = False,
    is_title: bool = False,
    override_mood: Optional[str] = None,
    override_pause_ms: Optional[int] = None,
) -> Dict[str, Any]:
    """Creates a single formatted sentence dictionary with speaker and voice metadata."""
    cleaned_raw = strip_cheesy_banter(raw_text)
    if not cleaned_raw:
        cleaned_raw = raw_text.strip()

    disp, spch, pause_ms, mood = analyze_sentence_cadence(
        cleaned_raw,
        idx=idx,
        is_paragraph_end=is_paragraph_end,
        is_title=is_title,
    )
    if override_mood:
        mood = override_mood
    if override_pause_ms is not None:
        pause_ms = override_pause_ms

    is_a = speaker.upper() == "A"
    return {
        "idx": idx,
        "display_text": disp,
        "speech_text": spch,
        "kind": kind,
        "pause_after_ms": pause_ms,
        "mood": mood,
        "speaker": "A" if is_a else "B",
        "speaker_name": "Anchor" if is_a else "Focus Partner",
        "voice_id": voice_a if is_a else voice_b,
    }


def _try_llm_focus_dialogue(
    title: str,
    paragraphs: List[str],
) -> Optional[List[Tuple[str, str]]]:
    """Optional lightweight AI pass if OPENAI_API_KEY and THEYA_ENABLE_LLM_DIALOGUE=1 are set.

    Strictly enforces Anti-Ping-Pong and Anti-Banter rules.
    """
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    enable_llm = os.environ.get("THEYA_ENABLE_LLM_DIALOGUE", "0").strip() == "1"
    if not api_key or not enable_llm:
        return None

    source_text = "\n\n".join(paragraphs[:20])
    system_prompt = (
        "You convert dense documents into a two-person Cognitive Focus Dialogue designed for "
        "learners who struggle to focus on walls of text.\n"
        "STRICT RULES:\n"
        "1. NO PING-PONG READING: Never just alternate reading paragraphs verbatim.\n"
        "2. NO CHEESY AI BANTER: Never say 'Welcome back to the deep dive', 'Buckle up', "
        "'Wow that's fascinating', or 'That's a great point'. Start immediately with the core thesis.\n"
        "3. ROLES:\n"
        "   - Speaker 'A' (Anchor): Explains the core facts, mechanisms, and arguments clearly.\n"
        "   - Speaker 'B' (Focus Partner): Steps in when an idea is dense to ask the exact grounding "
        "question a learner needs ('Hold on—what does that mean in plain terms?', 'Wait, why is that the bottleneck?') "
        "and synthesizes takeaways.\n"
        "Return ONLY valid JSON: {\"turns\": [{\"speaker\": \"A\"|\"B\", \"text\": \"...\"}]}"
    )

    payload = json.dumps({
        "model": os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Title: {title}\n\nDocument:\n{source_text}"},
        ],
        "temperature": 0.3,
    }).encode("utf-8")

    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=8.0) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            content = body["choices"][0]["message"]["content"]
            parsed = json.loads(content)
            turns = parsed.get("turns", [])
            result: List[Tuple[str, str]] = []
            for t in turns:
                spk = "B" if str(t.get("speaker", "A")).upper() == "B" else "A"
                txt = strip_cheesy_banter(str(t.get("text", "")).strip())
                if txt:
                    result.append((spk, txt))
            if len(result) >= 3:
                return result
    except Exception as exc:
        logger.debug("LLM dialogue pass skipped, using deterministic cognitive engine: %s", exc)
    return None


def shape_article_into_dialogue(
    title: str,
    paragraphs: List[str],
    voice_a: str = "en-US-AndrewMultilingualNeural",
    voice_b: str = "en-US-AvaMultilingualNeural",
) -> List[Dict[str, Any]]:
    """Transforms extracted paragraphs into a Two-Person Cognitive Focus Dialogue.

    Enforces:
    - Zero cheesy AI podcast banter.
    - Zero verbatim paragraph ping-ponging.
    - Active cognitive chunking: Anchor (Speaker A) delivers core thesis/evidence;
      Focus Partner (Speaker B) interrupts overload, asks clarifying questions, and locks in mental models.
    """
    segmenter = pysbd.Segmenter(language="en", clean=False)
    dialogue_sentences: List[Dict[str, Any]] = []
    current_idx = 0

    clean_title = strip_cheesy_banter(sanitize_for_podcast(title)) or "Focused Study Session"

    # Check if optional LLM pass is enabled and available
    llm_turns = _try_llm_focus_dialogue(clean_title, paragraphs)
    if llm_turns:
        dialogue_sentences.append(
            _build_turn(
                current_idx,
                clean_title,
                speaker="A",
                voice_a=voice_a,
                voice_b=voice_b,
                kind="title",
                is_title=True,
            )
        )
        current_idx += 1
        for spk, turn_text in llm_turns:
            sents = segmenter.segment(sanitize_for_podcast(turn_text))
            for s_i, s_raw in enumerate(sents):
                if not s_raw.strip():
                    continue
                dialogue_sentences.append(
                    _build_turn(
                        current_idx,
                        s_raw,
                        speaker=spk,
                        voice_a=voice_a,
                        voice_b=voice_b,
                        kind="prose",
                        is_paragraph_end=(s_i == len(sents) - 1),
                    )
                )
                current_idx += 1
        return dialogue_sentences

    # 1. Opening Title by Anchor (Speaker A)
    dialogue_sentences.append(
        _build_turn(
            current_idx,
            clean_title,
            speaker="A",
            voice_a=voice_a,
            voice_b=voice_b,
            kind="title",
            is_title=True,
            override_pause_ms=550,
        )
    )
    current_idx += 1

    # 2. Opening Focus Lock by Focus Partner (Speaker B) — sets cognitive intent without cheesy banter
    title_concept = _extract_focus_concept(clean_title)
    opening_focus = (
        f"Let's lock in on the core idea right away — as we break down {title_concept}, "
        "what is the main problem we are trying to solve?"
    )
    dialogue_sentences.append(
        _build_turn(
            current_idx,
            opening_focus,
            speaker="B",
            voice_a=voice_a,
            voice_b=voice_b,
            kind="prose",
            is_paragraph_end=True,
            override_mood="question",
            override_pause_ms=420,
        )
    )
    current_idx += 1

    # 3. Process paragraphs with Cognitive Load Chunking & Role Differentiation
    clarifier_cycle = 0
    for p_idx, raw_para in enumerate(paragraphs):
        para_clean = strip_cheesy_banter(sanitize_for_podcast(raw_para))
        if not para_clean:
            continue

        # Check if the user pasted an explicit script turn (e.g. "Speaker B: ...")
        explicit_match = SCRIPT_SPEAKER_REGEX.match(para_clean)
        if explicit_match:
            role_label = explicit_match.group(1).upper()
            content_body = explicit_match.group(2).strip()
            spk = "B" if any(k in role_label for k in ("B", "2", "CO", "CLARIFIER", "FOCUS", "Q")) else "A"
            for s_raw in segmenter.segment(content_body):
                if not s_raw.strip():
                    continue
                dialogue_sentences.append(
                    _build_turn(
                        current_idx,
                        s_raw,
                        speaker=spk,
                        voice_a=voice_a,
                        voice_b=voice_b,
                        kind="prose",
                        is_paragraph_end=True,
                    )
                )
                current_idx += 1
            continue

        raw_sents = [s.strip() for s in segmenter.segment(para_clean) if s.strip()]
        if not raw_sents:
            continue

        for s_idx, sent in enumerate(raw_sents):
            is_last_in_para = s_idx == len(raw_sents) - 1
            words = sent.split()
            concept = _extract_focus_concept(sent)

            # Case 1: Sentence starts with a sharp contrast ("However,", "Yet,", "Instead,")
            # Focus Partner (B) flags the pivot first so the learner's brain catches the turn!
            if CONTRAST_START_REGEX.search(sent):
                core_claim = CONTRAST_START_REGEX.sub("", sent).strip()
                if core_claim:
                    core_claim = core_claim[0].upper() + core_claim[1:]
                pivot_prompt = f"Hold on — here is the twist. Why does {concept} shift the picture?"
                dialogue_sentences.append(
                    _build_turn(
                        current_idx,
                        pivot_prompt,
                        speaker="B",
                        voice_a=voice_a,
                        voice_b=voice_b,
                        kind="prose",
                        override_mood="question",
                        override_pause_ms=260,
                    )
                )
                current_idx += 1

                dialogue_sentences.append(
                    _build_turn(
                        current_idx,
                        core_claim or sent,
                        speaker="A",
                        voice_a=voice_a,
                        voice_b=voice_b,
                        kind="prose",
                        is_paragraph_end=is_last_in_para,
                    )
                )
                current_idx += 1
                continue

            # Case 2: Sentence starts with a revelation trigger ("In fact,", "Crucially,")
            if REVELATION_START_REGEX.search(sent):
                core_rev = REVELATION_START_REGEX.sub("", sent).strip()
                if core_rev:
                    core_rev = core_rev[0].upper() + core_rev[1:]
                # Anchor states the core revelation
                dialogue_sentences.append(
                    _build_turn(
                        current_idx,
                        core_rev or sent,
                        speaker="A",
                        voice_a=voice_a,
                        voice_b=voice_b,
                        kind="prose",
                        override_mood="revelation",
                        override_pause_ms=300,
                    )
                )
                current_idx += 1

                # Focus Partner locks in why it matters
                lock_in = f"Let's lock that takeaway in — {concept} is the real lever here, not just surface details."
                dialogue_sentences.append(
                    _build_turn(
                        current_idx,
                        lock_in,
                        speaker="B",
                        voice_a=voice_a,
                        voice_b=voice_b,
                        kind="prose",
                        is_paragraph_end=is_last_in_para,
                        override_mood="punchy",
                        override_pause_ms=480,
                    )
                )
                current_idx += 1
                continue

            # Case 3: Sentence is a direct question in the text -> Route question to Focus Partner (B)
            if sent.endswith("?"):
                dialogue_sentences.append(
                    _build_turn(
                        current_idx,
                        sent,
                        speaker="B",
                        voice_a=voice_a,
                        voice_b=voice_b,
                        kind="prose",
                        override_mood="question",
                        override_pause_ms=320,
                    )
                )
                current_idx += 1
                continue

            # Case 4: High cognitive density sentence (> 17 words or multi-clause)
            # Split or follow up with Focus Partner unpacking it into plain terms
            setup_clause, takeaway_clause = _distill_dense_sentence(sent)
            if takeaway_clause:
                # Anchor delivers setup
                dialogue_sentences.append(
                    _build_turn(
                        current_idx,
                        setup_clause,
                        speaker="A",
                        voice_a=voice_a,
                        voice_b=voice_b,
                        kind="prose",
                        override_pause_ms=240,
                    )
                )
                current_idx += 1

                # Focus Partner interrupts to unpack the second half in plain English
                unpack_line = f"Wait — let's put that in plain terms: {takeaway_clause[0].lower() + takeaway_clause[1:] if len(takeaway_clause) > 1 else takeaway_clause}"
                dialogue_sentences.append(
                    _build_turn(
                        current_idx,
                        unpack_line,
                        speaker="B",
                        voice_a=voice_a,
                        voice_b=voice_b,
                        kind="prose",
                        is_paragraph_end=is_last_in_para,
                        override_mood="revelation",
                        override_pause_ms=460,
                    )
                )
                current_idx += 1
                continue

            # Standard delivery by Anchor (Speaker A)
            dialogue_sentences.append(
                _build_turn(
                    current_idx,
                    sent,
                    speaker="A",
                    voice_a=voice_a,
                    voice_b=voice_b,
                    kind="prose",
                    is_paragraph_end=is_last_in_para,
                )
            )
            current_idx += 1

            # If this paragraph had dense prose and Speaker B hasn't stepped in yet on this paragraph,
            # add a brief cognitive check-in at paragraph boundary so the listener never drifts.
            if is_last_in_para and len(words) >= 12:
                clarifier_prompts = [
                    f"Hold on — let's make sure that lands: why is {concept} the key piece to remember here?",
                    f"So if we strip away the complexity, {concept} is really what drives the outcome.",
                    f"Wait — pause on {concept} for a second. That is the exact mechanism everything else builds on.",
                ]
                prompt_text = clarifier_prompts[clarifier_cycle % len(clarifier_prompts)]
                clarifier_cycle += 1
                dialogue_sentences.append(
                    _build_turn(
                        current_idx,
                        prompt_text,
                        speaker="B",
                        voice_a=voice_a,
                        voice_b=voice_b,
                        kind="prose",
                        is_paragraph_end=True,
                        override_mood="question" if prompt_text.endswith("?") else "punchy",
                        override_pause_ms=420,
                    )
                )
                current_idx += 1

    return dialogue_sentences
