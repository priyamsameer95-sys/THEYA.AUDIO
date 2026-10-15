"""Quality gate: decide whether a tier's output is good enough to keep.

A failed Tier 1 usually looks like one of these:
* almost no text (bot wall, cookie wall, or JS-only content), or
* an SPA shell such as ``<div id="root"></div>`` with a "please enable
  JavaScript" notice, where Trafilatura finds a few stray words.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional, Union

from app import config
from app.extract.models import Extraction

SPA_MARKERS = re.compile(
    r"""<div[^>]+id=["'](?:root|app|__next|__nuxt|svelte)["'][^>]*>\s*</div>"""
    r"|(?:please\s+)?enable\s+javascript"
    r"|javascript\s+is\s+(?:disabled|required)"
    r"|requires\s+javascript",
    re.IGNORECASE,
)


@dataclass
class Verdict:
    ok: bool
    reasons: List[str] = field(default_factory=list)

    @property
    def summary(self) -> str:
        return ", ".join(self.reasons) if self.reasons else "ok"


def looks_like_spa_shell(html: Union[str, bytes, None]) -> bool:
    if not html:
        return False
    text = html.decode("latin-1", errors="ignore") if isinstance(html, bytes) else html
    return bool(SPA_MARKERS.search(text))


def assess(extraction: Optional[Extraction], html: Union[str, bytes, None] = None) -> Verdict:
    if extraction is None or not extraction.markdown.strip():
        return Verdict(ok=False, reasons=["no_content"])

    reasons: List[str] = []
    words = extraction.word_count
    if words < config.MIN_BODY_WORDS or len(extraction.markdown) < config.MIN_BODY_CHARS:
        reasons.append(f"too_short ({words} words)")
    if words < config.SPA_SUSPECT_MIN_WORDS and looks_like_spa_shell(html):
        reasons.append("spa_shell")
    return Verdict(ok=not reasons, reasons=reasons)
