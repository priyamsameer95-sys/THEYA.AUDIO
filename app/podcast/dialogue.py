"""Two-Person Cognitive Focus Dialogue Engine (Anti-Ping-Pong & Anti-Banter).

Designed specifically for learners who struggle with attention drift or dense text.
Instead of verbatim ping-pong reading or cheesy AI podcast banter, this engine pairs:
- Speaker A (Anchor): Presents the core thesis, mechanisms, and primary evidence clearly.
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

LEADING_DATELINE_REGEX = re.compile(
    r"^(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4}\s+(?=[A-Z\"“])"
)


def strip_cheesy_banter(text: str) -> str:
    """Removes banned cheesy AI podcast filler while preserving substantive prose."""
    cleaned = CHEESY_BANTER_REGEX.sub("", text)
    cleaned = LEADING_DATELINE_REGEX.sub("", cleaned)
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()
    return cleaned


def _distill_dense_sentence(sentence: str) -> Tuple[str, str, str]:
    """Splits an overloaded multi-clause sentence into (setup_clause, bridge_prompt, takeaway_clause)

    so working memory isn't overwhelmed and both voices collaborate on the single idea.
    Returns (sentence, "", "") if the sentence is already concise or cannot be cleanly split.
    """
    s = sentence.strip()

    # 1. Em-dash or spaced hyphen pivot (" — " or " - ")
    for sep in (" — ", " – ", " - "):
        if sep in s:
            parts = s.split(sep, 1)
            left, right = parts[0].strip(), parts[1].strip()
            if len(left.split()) >= 5 and len(right.split()) >= 4:
                right_clean = re.sub(r"^(?:and|but|so)\s+", "", right, flags=re.IGNORECASE).strip()
                if right_clean:
                    right_clean = right_clean[0].lower() + right_clean[1:]
                    return (
                        left if left.endswith((".", "!", "?")) else left + ".",
                        f"Wait — let's lock into that pivot: {right_clean}",
                        "pivot",
                    )

    # 2. Colon explanation (": ")
    if ": " in s and not s.lower().startswith("http"):
        parts = s.split(": ", 1)
        left, right = parts[0].strip(), parts[1].strip()
        if len(left.split()) >= 5 and len(right.split()) >= 4:
            right_clean = right[0].lower() + right[1:] if len(right) > 1 else right
            return (
                left + ".",
                f"Put in plain terms: {right_clean}",
                "unpack",
            )

    # 3. "because" causal mechanism
    if " because " in s:
        parts = s.split(" because ", 1)
        left, right = parts[0].strip(), parts[1].strip()
        if len(left.split()) >= 5 and len(right.split()) >= 4:
            return (
                left if left.endswith(".") else left + ".",
                f"Hold on — why does that happen? Because {right}",
                "mechanism",
            )

    # 4. ", which " relative consequence clause
    if ", which " in s:
        parts = s.split(", which ", 1)
        left, right = parts[0].strip(), parts[1].strip()
        if len(left.split()) >= 6 and len(right.split()) >= 4:
            return (
                left if left.endswith(".") else left + ".",
                f"And notice what that directly does: it {right}",
                "consequence",
            )

    # 5. " rather than " sharp contrast
    if " rather than " in s:
        parts = s.split(" rather than ", 1)
        left, right = parts[0].strip(), parts[1].strip()
        if len(left.split()) >= 7 and len(right.split()) >= 2:
            return (
                left if left.endswith(".") else left + ".",
                f"Notice that distinction — not through {right}",
                "contrast",
            )

    # 6. Semicolon compound thought ("; ")
    if "; " in s:
        parts = s.split("; ", 1)
        left, right = parts[0].strip(), parts[1].strip()
        if len(left.split()) >= 5 and len(right.split()) >= 4:
            right_clean = right[0].lower() + right[1:] if len(right) > 1 else right
            return (
                left if left.endswith(".") else left + ".",
                f"In other words, {right_clean}",
                "unpack",
            )

    return s, "", ""


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

    # Clean all paragraphs first and filter out empty/table-only noise
    cleaned_paragraphs: List[str] = []
    for raw_p in paragraphs:
        cp = strip_cheesy_banter(sanitize_for_podcast(raw_p))
        if cp and len(cp) > 2:
            cleaned_paragraphs.append(cp)

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
            override_pause_ms=500,
        )
    )
    current_idx += 1

    # Check if the very first sentence of the document is already a question
    first_para_sents = (
        [s.strip() for s in segmenter.segment(cleaned_paragraphs[0]) if s.strip()]
        if cleaned_paragraphs
        else []
    )
    first_sent_is_question = bool(first_para_sents and first_para_sents[0].endswith("?"))
    first_sent_is_explicit_script = bool(
        cleaned_paragraphs and SCRIPT_SPEAKER_REGEX.match(cleaned_paragraphs[0])
    )

    # 2. If document doesn't already open with a question or script prefix,
    # Focus Partner (Speaker B) sets the cognitive focus frame immediately.
    if not first_sent_is_question and not first_sent_is_explicit_script:
        opening_focus = (
            "Let's lock in on the core thesis right away — what is the main problem we are trying to solve here?"
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
                override_pause_ms=380,
            )
        )
        current_idx += 1

    # 3. Process paragraphs with Cognitive Load Chunking & Role Differentiation
    bridge_cycle = 0
    bridge_questions = [
        "Hold on — how does that actually work in practice?",
        "Wait — what is the core takeaway we should lock in from that?",
        "Let's pause there for a second — why does that distinction matter?",
        "Okay, so if that is the foundation, where does the argument go next?",
    ]
    takeaway_prefixes = [
        "Here is the key takeaway to lock in: ",
        "Put in plain terms: ",
        "So the bottom line here is simple: ",
        "Wait — pause on this point because it drives the rest: ",
    ]

    for p_idx, para_clean in enumerate(cleaned_paragraphs):
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

        raw_sents = [
            strip_cheesy_banter(s.strip())
            for s in segmenter.segment(para_clean)
            if strip_cheesy_banter(s.strip())
        ]
        if not raw_sents:
            continue

        speaker_b_used_in_para = False
        consecutive_a_in_para = 0

        for s_idx, sent in enumerate(raw_sents):
            is_last_in_para = s_idx == len(raw_sents) - 1
            words = sent.split()
            last_speaker = dialogue_sentences[-1]["speaker"] if dialogue_sentences else "A"

            # Case 1: Sentence is a direct question in the text
            # Route question to Focus Partner (B), UNLESS Speaker B just spoke and there's only 1 sentence!
            if sent.endswith("?"):
                target_spk = "B" if last_speaker == "A" or len(raw_sents) > 1 else "A"
                if target_spk == "B":
                    speaker_b_used_in_para = True
                    consecutive_a_in_para = 0
                else:
                    consecutive_a_in_para += 1
                dialogue_sentences.append(
                    _build_turn(
                        current_idx,
                        sent,
                        speaker=target_spk,
                        voice_a=voice_a,
                        voice_b=voice_b,
                        kind="prose",
                        override_mood="question",
                        override_pause_ms=340,
                    )
                )
                current_idx += 1
                continue

            # Case 2: Sentence starts with a sharp contrast ("However,", "Yet,", "Instead,")
            if CONTRAST_START_REGEX.search(sent):
                core_claim = CONTRAST_START_REGEX.sub("", sent).strip()
                if core_claim:
                    core_claim = core_claim[0].upper() + core_claim[1:]
                if last_speaker == "A":
                    pivot_prompt = "Hold on — here is the twist. How does the picture shift here?"
                    dialogue_sentences.append(
                        _build_turn(
                            current_idx,
                            pivot_prompt,
                            speaker="B",
                            voice_a=voice_a,
                            voice_b=voice_b,
                            kind="prose",
                            override_mood="question",
                            override_pause_ms=280,
                        )
                    )
                    current_idx += 1
                    speaker_b_used_in_para = True

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
                consecutive_a_in_para = 1
                continue

            # Case 3: Sentence starts with a revelation trigger ("In fact,", "Crucially,")
            if REVELATION_START_REGEX.search(sent):
                core_rev = REVELATION_START_REGEX.sub("", sent).strip()
                if core_rev:
                    core_rev = core_rev[0].lower() + core_rev[1:]
                # Focus Partner highlights the revelation directly in plain terms
                rev_line = f"Wait — lock this part in: {core_rev or sent}"
                dialogue_sentences.append(
                    _build_turn(
                        current_idx,
                        rev_line,
                        speaker="B",
                        voice_a=voice_a,
                        voice_b=voice_b,
                        kind="prose",
                        is_paragraph_end=is_last_in_para,
                        override_mood="revelation",
                        override_pause_ms=420,
                    )
                )
                current_idx += 1
                speaker_b_used_in_para = True
                consecutive_a_in_para = 0
                continue

            # Case 4: Multi-clause dense sentence -> Anchor delivers setup, Focus Partner unpacks second half
            setup_clause, unpack_turn, _ = _distill_dense_sentence(sent)
            if unpack_turn:
                dialogue_sentences.append(
                    _build_turn(
                        current_idx,
                        setup_clause,
                        speaker="A",
                        voice_a=voice_a,
                        voice_b=voice_b,
                        kind="prose",
                        override_pause_ms=250,
                    )
                )
                current_idx += 1

                dialogue_sentences.append(
                    _build_turn(
                        current_idx,
                        unpack_turn,
                        speaker="B",
                        voice_a=voice_a,
                        voice_b=voice_b,
                        kind="prose",
                        is_paragraph_end=is_last_in_para,
                        override_mood="revelation",
                        override_pause_ms=420,
                    )
                )
                current_idx += 1
                speaker_b_used_in_para = True
                consecutive_a_in_para = 0
                continue

            # Case 5: If Anchor has spoken 2+ sentences in a row and we are at the final takeaway sentence
            # of a multi-sentence paragraph, let Focus Partner (B) crystallize the concluding sentence!
            if (
                is_last_in_para
                and not speaker_b_used_in_para
                and consecutive_a_in_para >= 1
                and len(words) >= 6
            ):
                prefix = takeaway_prefixes[bridge_cycle % len(takeaway_prefixes)]
                bridge_cycle += 1
                sent_lower = (
                    sent[0].lower() + sent[1:]
                    if len(sent) > 1 and not sent[:2].isupper() and not sent.startswith("I ")
                    else sent
                )
                crystallized = f"{prefix}{sent_lower}"
                dialogue_sentences.append(
                    _build_turn(
                        current_idx,
                        crystallized,
                        speaker="B",
                        voice_a=voice_a,
                        voice_b=voice_b,
                        kind="prose",
                        is_paragraph_end=True,
                        override_mood="punchy",
                        override_pause_ms=440,
                    )
                )
                current_idx += 1
                speaker_b_used_in_para = True
                consecutive_a_in_para = 0
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
            consecutive_a_in_para += 1

            # Case 6: Single-sentence long paragraph where Speaker B hasn't stepped in yet
            # Insert a natural cognitive check-in question from Speaker B before the next paragraph
            if (
                is_last_in_para
                and not speaker_b_used_in_para
                and len(words) >= 14
                and p_idx < len(cleaned_paragraphs) - 1
            ):
                q_prompt = bridge_questions[bridge_cycle % len(bridge_questions)]
                bridge_cycle += 1
                dialogue_sentences.append(
                    _build_turn(
                        current_idx,
                        q_prompt,
                        speaker="B",
                        voice_a=voice_a,
                        voice_b=voice_b,
                        kind="prose",
                        is_paragraph_end=True,
                        override_mood="question",
                        override_pause_ms=380,
                    )
                )
                current_idx += 1
                speaker_b_used_in_para = True
                consecutive_a_in_para = 0

    return dialogue_sentences
