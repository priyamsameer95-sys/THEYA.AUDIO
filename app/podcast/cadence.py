"""Podcast Cadence Director & Prosody Engine.

Applies conversational podcast rhythm, deliberate pauses, emphasis markers,
and breathing room based on human podcasting speech dynamics.
"""
from __future__ import annotations

import re
from typing import Dict, List, Tuple


# Markers that signal a revelation, insight, or dramatic turn in speech
REVELATION_TRIGGERS = [
    r"\bthe truth is\b",
    r"\bin fact\b",
    r"\bcrucially\b",
    r"\bfundamentally\b",
    r"\bremarkably\b",
    r"\bsurprisingly\b",
    r"\bhere'?s the (?:thing|kicker|secret|catch)\b",
    r"\blet that sink in\b",
    r"\bthink about (?:it|that)\b",
    r"\bthe real question is\b",
    r"\bin other words\b",
    r"\bmake no mistake\b",
    r"\bpay attention to\b",
    r"\bwhat happened next\b",
    r"\band that changes everything\b",
    r"\bto put it simply\b",
    r"\bat the end of the day\b",
    r"\bnotice what happens here\b",
    r"\bwhy does this matter\b",
    r"\bpicture this\b",
    r"\band here is why\b",
    r"\band that is the point\b",
    r"\bthe fascinating part is\b",
    r"\bthe twist is\b",
    r"\bit turns out\b",
]

REVELATION_REGEX = re.compile("|".join(REVELATION_TRIGGERS), re.IGNORECASE)

# Contrast & transition markers
TRANSITION_TRIGGERS = [
    r"^(?:However|Yet|Meanwhile|Instead|Furthermore|On the other hand|In contrast|Consequently),",
    r"^(?:Now|So|Look|Listen),",
]
TRANSITION_REGEX = re.compile("|".join(TRANSITION_TRIGGERS), re.IGNORECASE)

# List / enumeration markers
ENUMERATION_TRIGGERS = [
    r"^(?:First(?:ly)?|Second(?:ly)?|Third(?:ly)?|Fourth|Finally|Lastly|To begin with),",
]
ENUMERATION_REGEX = re.compile("|".join(ENUMERATION_TRIGGERS), re.IGNORECASE)


def sanitize_for_podcast(text: str) -> str:
    """Cleans citation brackets, raw URLs, markdown syntax, and stiff artifacts unsuitable for podcast speech."""
    s = text.strip()
    # Strip markdown images ![alt](url)
    s = re.sub(r"!\[[^\]]*\]\([^\)]+\)", " ", s)
    # Convert markdown links [Text](url) -> Text
    s = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", s)
    # Remove citations like [1], [12], [citation needed]
    s = re.sub(r"\[\d+\]", "", s)
    s = re.sub(r"\[(?:citation needed|note)\]", "", s, flags=re.IGNORECASE)
    # Remove raw URLs
    s = re.sub(r"https?://\S+", "link", s)
    # Remove figure/table references like (Figure 1), (see Table 2)
    s = re.sub(r"\((?:see\s+)?(?:Figure|Fig\.|Table)\s*\d+[a-z]?\)", "", s, flags=re.IGNORECASE)
    # Strip markdown table separator rows and stray pipes
    s = re.sub(r"^\s*\|[\s\-:|]+\|\s*$", "", s)
    s = re.sub(r"(?:\|\s*)+", " ", s)
    # Strip markdown bold/italic asterisks
    s = re.sub(r"\*{1,3}", "", s)
    # Clean redundant whitespace
    s = re.sub(r"\s+", " ", s).strip()
    return s


def analyze_sentence_cadence(
    raw_sentence: str,
    idx: int,
    is_paragraph_end: bool = False,
    is_title: bool = False,
) -> Tuple[str, str, int, str]:
    """Analyzes a sentence and computes its podcast speech representation,

    recommended pause time, and mood.

    Returns:
        (display_text, speech_text, pause_after_ms, mood)
    """
    display = sanitize_for_podcast(raw_sentence)
    if not display:
        return ("", "", 150, "neutral")

    if is_title:
        # Title/Hook: slower, confident delivery with long pause
        speech = f"{display}." if not display.endswith((".", "!", "?")) else display
        speech = f"<break time=\"200ms\"/> {speech}"
        return (display, speech, 800, "hook")

    # Convert parentheticals into natural acoustic asides
    display = re.sub(r"\(([A-Za-z0-9\s,–—'\"]{3,60})\)", r"— \1 —", display)

    # Detect rhetorical or reflective question
    is_question = display.endswith("?")
    is_revelation = bool(REVELATION_REGEX.search(display))
    is_transition = bool(TRANSITION_REGEX.search(display))
    is_enumeration = bool(ENUMERATION_REGEX.search(display))
    is_quote = (display.startswith(("“", "\"", "‘")) and display.endswith(("”", "\"", "’")))
    words = display.split()
    is_punchy = len(words) <= 4 and display.endswith((".", "!")) and not is_question

    speech = display

    # 1. Pacing within sentence: replace em-dash and colon with deliberate breathing breaks
    if "—" in speech:
        speech = speech.replace("—", " — <break time=\"250ms\"/> ")
    if ": " in speech and not speech.startswith("http"):
        speech = speech.replace(": ", ": <break time=\"300ms\"/> ")

    # 2. Add dramatic emphasis around revelation triggers
    if is_revelation:
        # Prepend subtle pause before crucial insight
        speech = f"<break time=\"200ms\"/> {speech}"
        mood = "revelation"
        pause_ms = 600 if is_paragraph_end else 450
    elif is_question:
        # Question: let the question hang in the air for the listener
        mood = "question"
        pause_ms = 700 if is_paragraph_end else 550
    elif is_punchy:
        # Short punchy takeaway
        mood = "punchy"
        pause_ms = 580 if is_paragraph_end else 450
    elif is_enumeration:
        mood = "enumeration"
        pause_ms = 480 if is_paragraph_end else 320
    elif is_quote:
        mood = "quote"
        pause_ms = 500 if is_paragraph_end else 350
    elif is_transition:
        mood = "transition"
        pause_ms = 400 if is_paragraph_end else 250
    else:
        mood = "narrative"
        pause_ms = 650 if is_paragraph_end else 220

    # Ensure speech ends with clean punctuation for neural engine
    if not speech.endswith((".", "!", "?", "—")):
        speech += "."

    return (display, speech, pause_ms, mood)


def shape_article_into_podcast(
    title: str,
    paragraphs: List[str],
) -> List[Dict]:
    """Converts a sequence of paragraphs into a structured podcast script with cadence."""
    import pysbd
    segmenter = pysbd.Segmenter(language="en", clean=False)
    podcast_sentences: List[Dict] = []
    current_idx = 0

    # 1. Opening Hook / Title
    disp, spch, pause_ms, mood = analyze_sentence_cadence(title, current_idx, is_title=True)
    podcast_sentences.append({
        "idx": current_idx,
        "display_text": disp,
        "speech_text": spch,
        "kind": "title",
        "pause_after_ms": pause_ms,
        "mood": mood,
    })
    current_idx += 1

    # 2. Iterate paragraphs
    for p_idx, para in enumerate(paragraphs):
        para_clean = sanitize_for_podcast(para)
        if not para_clean:
            continue

        raw_sents = segmenter.segment(para_clean)
        num_sents = len(raw_sents)

        for s_idx, raw_s in enumerate(raw_sents):
            if not raw_s.strip():
                continue
            is_p_end = (s_idx == num_sents - 1)
            disp, spch, pause_ms, mood = analyze_sentence_cadence(
                raw_s, current_idx, is_paragraph_end=is_p_end, is_title=False
            )
            podcast_sentences.append({
                "idx": current_idx,
                "display_text": disp,
                "speech_text": spch,
                "kind": "prose",
                "pause_after_ms": pause_ms,
                "mood": mood,
            })
            current_idx += 1

    return podcast_sentences
