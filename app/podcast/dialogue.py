"""Two-Person Conversational Thought-Sharing & Cognitive Focus Engine.

Transforms static articles, essays, PDFs, and notes into an authentic two-person
working session between two thinkers:
- Speaker A (Anchor / Strategist): Frames the thesis, reframes written prose into
  spoken reasoning, and traces mechanisms.
- Speaker B (Focus Partner / First-Principles Thinker): Reacts in real time,
  challenges assumptions, asks the exact question a listener is thinking, and
  synthesizes mental models—never reading verbatim paragraphs or using cheesy AI banter.
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

# Boilerplate / Paywall / Newsletter Promo patterns that real humans never read aloud
BOILERPLATE_PATTERNS: List[str] = [
    r"if you[’']?d like to upgrade to receive",
    r"upgrade below",
    r"new reports added every month",
    r"subscribe to receive",
    r"sign up for our newsletter",
    r"paid subscribers",
    r"table skipped for audio playback",
    r"code block skipped for audio playback",
    r"all rights reserved",
    r"share this post",
    r"^\s*🔒",
    r"goes deeper into the concepts and ideas that are covered in the weekly briefing",
]

BOILERPLATE_REGEX = re.compile("|".join(BOILERPLATE_PATTERNS), re.IGNORECASE)

# Explicit script speaker prefix detection (if user pastes a pre-formatted dialogue)
SCRIPT_SPEAKER_REGEX = re.compile(
    r"^\s*(?:\*\*)?(Speaker\s*[AB12]|Host(?:\s*[AB12])?|Co-?Host|Anchor|Clarifier|Focus Partner|Alex|Maya|Q|A)(?:\*\*)?\s*:\s*(.+)$",
    re.IGNORECASE,
)

LEADING_DATELINE_REGEX = re.compile(
    r"^(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4}\s+(?=[A-Z\"“])"
)


def strip_cheesy_banter(text: str) -> str:
    """Removes banned cheesy AI podcast filler and leading datelines while preserving substantive prose."""
    cleaned = CHEESY_BANTER_REGEX.sub("", text)
    cleaned = LEADING_DATELINE_REGEX.sub("", cleaned)
    cleaned = re.sub(r"^[🔒🎧📩💡✨]+\s*", "", cleaned)
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()
    return cleaned


def _is_boilerplate(text: str) -> bool:
    """Detects newsletter paywall blurbs, upgrade CTAs, and non-article chrome."""
    s = text.strip()
    if not s or len(s) < 4:
        return True
    if BOILERPLATE_REGEX.search(s):
        return True
    return False


def _reframe_written_to_spoken(sentence: str) -> str:
    """Transforms stiff written or first-person authorial sentences into natural spoken reasoning

    so hosts sound like they are discussing the ideas rather than reading a diary verbatim.
    """
    s = strip_cheesy_banter(sentence)
    if not s:
        return ""

    # 1. Reframe first-person authorial statements ("I decided to...", "Partly my goal was...")
    first_person_rewrites: List[Tuple[str, str]] = [
        (
            r"^I decided to find out by making it\.?$",
            "That is what the author actually set out to test by building it from scratch.",
        ),
        (
            r"^I decided to\s+(.+)$",
            r"The author set out to \1",
        ),
        (
            r"^Partly my goal was to\s+(.+)$",
            r"On one level, the practical goal here is to \1",
        ),
        (
            r"^My goal was to\s+(.+)$",
            r"The core goal here is to \1",
        ),
        (
            r"^But I was also curious about\s+(.+)$",
            r"At the same time, there is a deeper question underneath about \1",
        ),
        (
            r"^I was also curious about\s+(.+)$",
            r"There is also a deeper question here about \1",
        ),
        (
            r"^And one result of this exercise is that\s+(.+)$",
            r"And what actually emerges when you map that out is that \1",
        ),
        (
            r"^In my experience,?\s+(.+)$",
            r"When you look at how this plays out in the real world, \1",
        ),
        (
            r"^I think\s+(.+)$",
            r"The core argument here is that \1",
        ),
        (
            r"^I believe\s+(.+)$",
            r"The underlying conviction here is that \1",
        ),
        (
            r"^What I found (?:was|is) that\s+(.+)$",
            r"What actually shows up when you test this is that \1",
        ),
        (
            r"^When ([^,]+?) said this (?:last year|recently), it certainly raised a few eyebrows:?$",
            r"Look at what \1 pointed out recently — it really challenged the default consensus.",
        ),
        (
            r"^In (?:his|her|their) eyes,\s+(.+)$",
            r"The argument is that \1",
        ),
    ]
    for pattern, replacement in first_person_rewrites:
        if re.match(pattern, s, flags=re.IGNORECASE):
            s = re.sub(pattern, replacement, s, flags=re.IGNORECASE)
            break

    # 2. Replace mid-sentence first-person pronouns when referring to the essay author
    s = re.sub(r"\bmy goal was\b", "the goal was", s, flags=re.IGNORECASE)
    s = re.sub(r"\bI decided to\b", "the author decided to", s)

    # 3. Replace stiff written transitions with spoken conversational transitions
    written_to_spoken_transitions: List[Tuple[str, str]] = [
        (r"^Furthermore,\s+", "And building right on top of that, "),
        (r"^Moreover,\s+", "What's more, "),
        (r"^Consequently,\s+", "So the direct result of that is "),
        (r"^Therefore,\s+", "Which means "),
        (r"^Thus,\s+", "So in practice, "),
        (r"^Subsequently,\s+", "Right after that, "),
        (r"^Nevertheless,\s+", "Even with all of that, "),
        (r"^Nonetheless,\s+", "Still, "),
    ]
    for pattern, replacement in written_to_spoken_transitions:
        s = re.sub(pattern, replacement, s, flags=re.IGNORECASE)

    # Clean trailing colons into periods for natural spoken cadence
    if s.endswith(":"):
        s = s[:-1] + "."

    return s.strip()


def _lowercase_leading_unless_proper(text: str) -> str:
    """Lowercases the first letter of a clause unless it starts with 'I ' or an acronym/proper noun."""
    s = text.strip()
    if len(s) < 2:
        return s
    first_word = s.split()[0].strip(",.:;\"'()")
    # Keep uppercase if acronym (e.g. AI, CEO, API, LLM, PDF) or known proper starts
    if first_word.isupper() or first_word in (
        "I", "Linear", "Linear's", "OpenAI", "OpenAI's", "Google", "Apple", "Microsoft",
        "Byzantine", "Paul", "Graham", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday",
    ):
        return s
    return s[0].lower() + s[1:]


def _conversational_decompose(sentence: str) -> Optional[List[Tuple[str, str, str]]]:
    """Decomposes a complex sentence into a genuine multi-turn thought-sharing exchange:

    Returns a list of (speaker, spoken_text, mood) turns if the sentence contains a rich
    pivot, contrast, causal mechanism, or implication; otherwise returns None.
    """
    s = _reframe_written_to_spoken(sentence)
    if not s:
        return None

    # Pattern 1: "was over - and in its place was ..." / Old Era vs New Era shift
    m_shift = re.search(
        r"^(.+?)\s+(?:—|–|-)\s+(?:and\s+)?in its place (?:was|is)\s+(.+)$",
        s,
        flags=re.IGNORECASE,
    )
    if m_shift:
        old_way = m_shift.group(1).strip().rstrip(".,") + "."
        new_way = _lowercase_leading_unless_proper(m_shift.group(2).strip().rstrip(".")) + "."
        return [
            ("A", old_way, "narrative"),
            (
                "B",
                "Wait — if that playbook is over, what actually replaces it? Because teams still need a lever that compounds.",
                "question",
            ),
            (
                "A",
                f"What takes its place is {new_way}",
                "revelation",
            ),
            (
                "B",
                "See, that shift makes total sense — once the old shortcuts saturate, quality is the only thing users actually feel.",
                "punchy",
            ),
        ]

    # Pattern 2: "rather than" contrast (e.g. "differentiate through X rather than Y")
    if " rather than " in s:
        parts = s.split(" rather than ", 1)
        left, right = parts[0].strip().rstrip(".,"), parts[1].strip().rstrip(".")
        if len(left.split()) >= 6 and len(right.split()) >= 2:
            left_spoken = _lowercase_leading_unless_proper(left)
            return [
                (
                    "A",
                    f"Look at what's happening next: {left_spoken}.",
                    "narrative",
                ),
                (
                    "B",
                    f"Hold on — notice what's NOT on that list. We're talking about standing out through those fundamentals, rather than just relying on {right}.",
                    "revelation",
                ),
                (
                    "A",
                    f"Exactly. Once {right} becomes a commodity everyone can access, the real moat moves back to human execution and trust.",
                    "punchy",
                ),
            ]

    # Pattern 3: Semicolon contrast ("it has a definite shape; it's not just a list of bland truisms")
    if "; " in s:
        parts = s.split("; ", 1)
        left, right = parts[0].strip(), parts[1].strip().rstrip(".")
        if len(left.split()) >= 4 and len(right.split()) >= 4:
            right_spoken = _lowercase_leading_unless_proper(right)
            return [
                ("A", left + ".", "narrative"),
                (
                    "B",
                    "Wait — when most people try to map something that broad, doesn't it usually turn into generic advice?",
                    "question",
                ),
                (
                    "A",
                    f"That's the surprising takeaway here: {right_spoken}.",
                    "revelation",
                ),
            ]

    # Pattern 4: "because" causal mechanism
    if " because " in s:
        parts = s.split(" because ", 1)
        left, right = parts[0].strip().rstrip("."), parts[1].strip().rstrip(".")
        if len(left.split()) >= 5 and len(right.split()) >= 4:
            right_spoken = _lowercase_leading_unless_proper(right)
            return [
                ("A", f"{left}.", "narrative"),
                (
                    "B",
                    "Let's pause on the mechanism there — why does that actually happen under the hood?",
                    "question",
                ),
                (
                    "A",
                    f"It comes down to this: {right_spoken}.",
                    "revelation",
                ),
            ]

    # Pattern 5: Em-dash or spaced-hyphen insight (" — " or " - ")
    for sep in (" — ", " – ", " - "):
        if sep in s:
            parts = s.split(sep, 1)
            left, right = parts[0].strip().rstrip("."), parts[1].strip().rstrip(".")
            if len(left.split()) >= 5 and len(right.split()) >= 4:
                right_clean = re.sub(r"^(?:and|but|so)\s+", "", right, flags=re.IGNORECASE).strip()
                right_spoken = _lowercase_leading_unless_proper(right_clean)
                return [
                    ("A", f"{left}.", "narrative"),
                    (
                        "B",
                        f"And think about what that means in practice — {right_spoken}.",
                        "revelation",
                    ),
                ]

    # Pattern 6: Colon explanation (": ")
    if ": " in s and not s.lower().startswith("http"):
        parts = s.split(": ", 1)
        left, right = parts[0].strip().rstrip("."), parts[1].strip().rstrip(".")
        if len(left.split()) >= 4 and len(right.split()) >= 4:
            right_spoken = _lowercase_leading_unless_proper(right)
            return [
                ("A", f"{left}.", "narrative"),
                (
                    "B",
                    f"Put simply, here is what that looks like on the ground: {right_spoken}.",
                    "revelation",
                ),
            ]

    # Pattern 7: ", which " consequence clause
    if ", which " in s:
        parts = s.split(", which ", 1)
        left, right = parts[0].strip().rstrip("."), parts[1].strip().rstrip(".")
        if len(left.split()) >= 5 and len(right.split()) >= 4:
            right_spoken = _lowercase_leading_unless_proper(right)
            return [
                ("A", f"{left}.", "narrative"),
                (
                    "B",
                    f"And follow the chain reaction of that — it directly {right_spoken}.",
                    "revelation",
                ),
            ]

    return None


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
    """Uses Hugging Face InferenceClient (HF_TOKEN), Gemini, Groq, or OpenAI if available

    to generate a deep 2-person thought-sharing podcast conversation.
    Falls back gracefully if no key/server is present.
    """
    hf_key = os.environ.get("HF_TOKEN", "").strip()
    gemini_key = os.environ.get("GEMINI_API_KEY", "").strip()
    openai_key = os.environ.get("OPENAI_API_KEY", "").strip()
    groq_key = os.environ.get("GROQ_API_KEY", "").strip()

    if not (hf_key or gemini_key or openai_key or groq_key):
        return None

    source_text = "\n\n".join(paragraphs[:20])
    system_prompt = (
        "You are producing an authentic two-person intellectual working session (Speaker 'A' and Speaker 'B') "
        "for listeners who want to deeply understand a document without reading walls of text.\n"
        "CRITICAL RULES:\n"
        "1. NEVER READ VERBATIM: Do not just chop sentences in half or alternate reading paragraphs.\n"
        "2. NO CHEESY AI PODCAST BANTER: Never say 'Welcome back to the deep dive', 'Buckle up', "
        "'Wow that's fascinating', or 'That's a great point'.\n"
        "3. ACTUALLY WORK THROUGH THE IDEAS: Have Speaker A and Speaker B think out loud, challenge premises, "
        "paraphrase the author's arguments into natural spoken English, ask 'Wait, why does that work?', "
        "and share concrete mental models.\n"
        "Return ONLY valid JSON: {\"turns\": [{\"speaker\": \"A\"|\"B\", \"text\": \"...\"}]}"
    )

    try:
        if hf_key:
            from huggingface_hub import InferenceClient

            hf_client = InferenceClient(api_key=hf_key)
            chat_res = hf_client.chat_completion(
                model="Qwen/Qwen2.5-72B-Instruct",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Title: {title}\n\nDocument:\n{source_text}"},
                ],
                max_tokens=1800,
                temperature=0.35,
            )
            raw_content = chat_res.choices[0].message.content or ""
            # Extract JSON object even if wrapped in markdown fences
            m_json = re.search(r"\{[\s\S]*\}", raw_content)
            if m_json:
                parsed = json.loads(m_json.group(0))
                turns = parsed.get("turns", [])
                result = [
                    (
                        "B" if str(t.get("speaker", "A")).upper() == "B" else "A",
                        strip_cheesy_banter(str(t.get("text", ""))),
                    )
                    for t in turns
                    if str(t.get("text", "")).strip()
                ]
                if len(result) >= 4:
                    return result

        if gemini_key:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={gemini_key}"
            payload = json.dumps({
                "contents": [{"parts": [{"text": f"{system_prompt}\n\nTitle: {title}\n\nDocument:\n{source_text}"}]}],
                "generationConfig": {"responseMimeType": "application/json", "temperature": 0.35},
            }).encode("utf-8")
            req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
            with urllib.request.urlopen(req, timeout=10.0) as resp:
                body = json.loads(resp.read().decode("utf-8"))
                content = body["candidates"][0]["content"]["parts"][0]["text"]
                parsed = json.loads(content)
                turns = parsed.get("turns", [])
                result = [
                    ("B" if str(t.get("speaker", "A")).upper() == "B" else "A", strip_cheesy_banter(str(t.get("text", ""))))
                    for t in turns
                    if str(t.get("text", "")).strip()
                ]
                if len(result) >= 4:
                    return result

        api_key = groq_key or openai_key
        endpoint = (
            "https://api.groq.com/openai/v1/chat/completions"
            if groq_key
            else "https://api.openai.com/v1/chat/completions"
        )
        model = "llama-3.3-70b-versatile" if groq_key else os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
        payload = json.dumps({
            "model": model,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Title: {title}\n\nDocument:\n{source_text}"},
            ],
            "temperature": 0.35,
        }).encode("utf-8")
        req = urllib.request.Request(
            endpoint,
            data=payload,
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10.0) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            content = body["choices"][0]["message"]["content"]
            parsed = json.loads(content)
            turns = parsed.get("turns", [])
            result = [
                ("B" if str(t.get("speaker", "A")).upper() == "B" else "A", strip_cheesy_banter(str(t.get("text", ""))))
                for t in turns
                if str(t.get("text", "")).strip()
            ]
            if len(result) >= 4:
                return result
    except Exception as exc:
        logger.debug("LLM dialogue pass skipped, using conversational discourse engine: %s", exc)
    return None


def shape_article_into_dialogue(
    title: str,
    paragraphs: List[str],
    voice_a: str = "en-US-AndrewMultilingualNeural",
    voice_b: str = "en-US-AvaMultilingualNeural",
) -> List[Dict[str, Any]]:
    """Transforms extracted paragraphs into an authentic Two-Person Conversational Working Session.

    Enforces:
    - Zero cheesy AI podcast banter.
    - Zero verbatim paragraph ping-ponging or mechanical sentence chopping.
    - Active thought-sharing: Written sentences are reframed into spoken reasoning,
      boilerplate/paywall promos are stripped, and both hosts challenge and build on ideas.
    """
    segmenter = pysbd.Segmenter(language="en", clean=False)
    dialogue_sentences: List[Dict[str, Any]] = []
    current_idx = 0

    clean_title = strip_cheesy_banter(sanitize_for_podcast(title)).rstrip(".") or "Focused Study Session"

    # Filter out paywall/newsletter boilerplate paragraphs first
    cleaned_paragraphs: List[str] = []
    for raw_p in paragraphs:
        cp = strip_cheesy_banter(sanitize_for_podcast(raw_p))
        if cp and not _is_boilerplate(cp):
            cleaned_paragraphs.append(cp)

    if not cleaned_paragraphs and paragraphs:
        # Fallback if every single paragraph matched boilerplate filter
        for raw_p in paragraphs:
            cp = strip_cheesy_banter(sanitize_for_podcast(raw_p))
            if cp:
                cleaned_paragraphs.append(cp)

    # Check if optional LLM pass is available
    llm_turns = _try_llm_focus_dialogue(clean_title, cleaned_paragraphs)
    if llm_turns:
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

    # Check if the user pasted an explicit script ("A: ... / B: ...")
    has_explicit_script = bool(
        cleaned_paragraphs and SCRIPT_SPEAKER_REGEX.match(cleaned_paragraphs[0])
    )

    if not has_explicit_script:
        # 1. Conversational Studio Opening — two thinkers sitting down with the material
        opening_a = f"We're working through {clean_title} today, and I want to get straight to the core thesis underneath this piece."
        dialogue_sentences.append(
            _build_turn(
                current_idx,
                opening_a,
                speaker="A",
                voice_a=voice_a,
                voice_b=voice_b,
                kind="title",
                is_title=True,
                override_pause_ms=420,
            )
        )
        current_idx += 1

        first_sents = (
            [s.strip() for s in segmenter.segment(cleaned_paragraphs[0]) if s.strip() and not _is_boilerplate(s)]
            if cleaned_paragraphs
            else []
        )
        first_is_q = bool(first_sents and first_sents[0].endswith("?"))

        if not first_is_q:
            opening_b = (
                "Yeah, let's strip away the surface noise right away — what is the central problem or shift we need to lock in on here?"
            )
            dialogue_sentences.append(
                _build_turn(
                    current_idx,
                    opening_b,
                    speaker="B",
                    voice_a=voice_a,
                    voice_b=voice_b,
                    kind="prose",
                    is_paragraph_end=True,
                    override_mood="question",
                    override_pause_ms=360,
                )
            )
            current_idx += 1

    # Conversational reaction & thought-sharing templates for multi-sentence flow
    cohost_reactions_to_a = [
        "Wait — think about the implication of that for a second. How does that play out when you actually apply it?",
        "Hold on, let me push on that slightly — why doesn't the standard approach solve that already?",
        "Right, and if we follow that logic one step further, what is the real bottleneck?",
        "See, that's the part most people gloss over. Where does the argument take that next?",
    ]
    cohost_synthesis_leadins = [
        "And here is how I'm connecting that: ",
        "If you think about what that actually means on the ground, ",
        "Look at the bigger picture this points to — ",
        "And that brings us to the real takeaway here: ",
    ]
    anchor_leadins = [
        "Look at how the piece frames this: ",
        "Here's the mechanism behind that — ",
        "What's really happening here is that ",
        "Follow that thread for a second: ",
    ]
    reaction_cycle = 0
    synthesis_cycle = 0
    anchor_cycle = 0

    for p_idx, para_clean in enumerate(cleaned_paragraphs):
        # Handle explicit script turns ("Speaker A: ...", "Speaker B: ...")
        explicit_match = SCRIPT_SPEAKER_REGEX.match(para_clean)
        if explicit_match:
            role_label = explicit_match.group(1).upper()
            content_body = explicit_match.group(2).strip()
            spk = "B" if any(k in role_label for k in ("B", "2", "CO", "CLARIFIER", "FOCUS", "MAYA", "Q")) else "A"
            for s_raw in segmenter.segment(content_body):
                s_clean = strip_cheesy_banter(s_raw.strip())
                if not s_clean:
                    continue
                dialogue_sentences.append(
                    _build_turn(
                        current_idx,
                        s_clean,
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
            if strip_cheesy_banter(s.strip()) and not _is_boilerplate(s)
        ]
        if not raw_sents:
            continue

        s_cursor = 0
        while s_cursor < len(raw_sents):
            sent = raw_sents[s_cursor]
            is_last_in_para = s_cursor == len(raw_sents) - 1
            last_speaker = dialogue_sentences[-1]["speaker"] if dialogue_sentences else "A"

            # 1. If the sentence is a question in the source text, have Focus Partner (B)
            # frame it as a live thought experiment!
            if sent.endswith("?"):
                q_spoken = _reframe_written_to_spoken(sent)
                if not q_spoken.lower().startswith(("right", "think", "wait", "hold", "what", "how", "why")):
                    q_spoken = f"Think about the question at the heart of this: {_lowercase_leading_unless_proper(q_spoken)}"
                elif last_speaker == "A":
                    q_spoken = f"Right — and ask yourself this: {_lowercase_leading_unless_proper(q_spoken)}"
                dialogue_sentences.append(
                    _build_turn(
                        current_idx,
                        q_spoken,
                        speaker="B",
                        voice_a=voice_a,
                        voice_b=voice_b,
                        kind="prose",
                        override_mood="question",
                        override_pause_ms=360,
                    )
                )
                current_idx += 1
                s_cursor += 1
                continue

            # 2. Check if this sentence has a rich internal contrast/shift/mechanism that
            # decomposes into a natural multi-turn back-and-forth exchange!
            decomposed = _conversational_decompose(sent)
            if decomposed:
                for d_i, (d_spk, d_txt, d_mood) in enumerate(decomposed):
                    dialogue_sentences.append(
                        _build_turn(
                            current_idx,
                            d_txt,
                            speaker=d_spk,
                            voice_a=voice_a,
                            voice_b=voice_b,
                            kind="prose",
                            is_paragraph_end=(is_last_in_para and d_i == len(decomposed) - 1),
                            override_mood=d_mood,
                            override_pause_ms=380 if d_mood in ("question", "punchy", "revelation") else 260,
                        )
                    )
                    current_idx += 1
                s_cursor += 1
                continue

            # 3. Check if sentence starts with a contrast ("However,", "But,", "Yet,", "Instead,")
            m_contrast = re.match(
                r"^(?:However|Yet|But|Instead|On the other hand|In contrast|Conversely),?\s+(.+)$",
                sent,
                flags=re.IGNORECASE,
            )
            if m_contrast:
                core_rest = _reframe_written_to_spoken(m_contrast.group(1).strip())
                core_lower = _lowercase_leading_unless_proper(core_rest)
                if last_speaker == "A":
                    dialogue_sentences.append(
                        _build_turn(
                            current_idx,
                            "Hold on, though — there's a catch to that if we look closer, isn't there?",
                            speaker="B",
                            voice_a=voice_a,
                            voice_b=voice_b,
                            kind="prose",
                            override_mood="question",
                            override_pause_ms=300,
                        )
                    )
                    current_idx += 1
                    dialogue_sentences.append(
                        _build_turn(
                            current_idx,
                            f"Exactly — {core_lower}",
                            speaker="A",
                            voice_a=voice_a,
                            voice_b=voice_b,
                            kind="prose",
                            is_paragraph_end=is_last_in_para,
                            override_mood="revelation",
                            override_pause_ms=380,
                        )
                    )
                    current_idx += 1
                else:
                    dialogue_sentences.append(
                        _build_turn(
                            current_idx,
                            f"Wait — here is the flip side to that: {core_lower}",
                            speaker="B",
                            voice_a=voice_a,
                            voice_b=voice_b,
                            kind="prose",
                            is_paragraph_end=is_last_in_para,
                            override_mood="revelation",
                            override_pause_ms=380,
                        )
                    )
                    current_idx += 1
                s_cursor += 1
                continue

            # 4. Pairwise Conversational Collaboration across consecutive sentences in a paragraph!
            # Instead of reading Sentence 1 and Sentence 2 flatly, Anchor reframes Sentence 1,
            # and Focus Partner connects Sentence 2 as an active shared insight!
            spoken_s1 = _reframe_written_to_spoken(sent)
            if s_cursor == 0 and p_idx > 0 and not spoken_s1.lower().startswith(("look", "that", "on one", "the ", "what")):
                lead = anchor_leadins[anchor_cycle % len(anchor_leadins)]
                anchor_cycle += 1
                spoken_s1 = f"{lead}{_lowercase_leading_unless_proper(spoken_s1)}"

            dialogue_sentences.append(
                _build_turn(
                    current_idx,
                    spoken_s1,
                    speaker="A",
                    voice_a=voice_a,
                    voice_b=voice_b,
                    kind="prose",
                    is_paragraph_end=is_last_in_para,
                )
            )
            current_idx += 1

            # If there is a next sentence in this paragraph (and it's not a question or decomposed turn),
            # have Focus Partner (Speaker B) synthesize it as a conversational response!
            if s_cursor + 1 < len(raw_sents):
                next_sent = raw_sents[s_cursor + 1]
                if not next_sent.endswith("?") and _conversational_decompose(next_sent) is None:
                    spoken_s2 = _reframe_written_to_spoken(next_sent)
                    lead_b = cohost_synthesis_leadins[synthesis_cycle % len(cohost_synthesis_leadins)]
                    synthesis_cycle += 1
                    b_turn = f"{lead_b}{_lowercase_leading_unless_proper(spoken_s2)}"
                    dialogue_sentences.append(
                        _build_turn(
                            current_idx,
                            b_turn,
                            speaker="B",
                            voice_a=voice_a,
                            voice_b=voice_b,
                            kind="prose",
                            is_paragraph_end=(s_cursor + 1 == len(raw_sents) - 1),
                            override_mood="revelation",
                            override_pause_ms=400,
                        )
                    )
                    current_idx += 1
                    s_cursor += 2
                    continue

            # If this was a single-sentence paragraph, have Focus Partner react to set up the next paragraph
            if is_last_in_para and p_idx < len(cleaned_paragraphs) - 1:
                reaction_q = cohost_reactions_to_a[reaction_cycle % len(cohost_reactions_to_a)]
                reaction_cycle += 1
                dialogue_sentences.append(
                    _build_turn(
                        current_idx,
                        reaction_q,
                        speaker="B",
                        voice_a=voice_a,
                        voice_b=voice_b,
                        kind="prose",
                        is_paragraph_end=True,
                        override_mood="question",
                        override_pause_ms=360,
                    )
                )
                current_idx += 1

            s_cursor += 1

    return dialogue_sentences
