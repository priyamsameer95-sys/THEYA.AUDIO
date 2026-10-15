"""Central configuration for theya.voice.

Every tunable lives here as an UPPER_SNAKE_CASE constant so no magic numbers
hide inside the pipeline. Values can be overridden with ``THEYA_*`` env vars.
"""
from __future__ import annotations

import os


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    return float(raw) if raw else default


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    return int(raw) if raw else default


# --- Fetching (Tier 1) -------------------------------------------------------
# A realistic desktop browser UA: many sites block "python-httpx/x.y".
USER_AGENT = os.getenv(
    "THEYA_USER_AGENT",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
)
FETCH_TIMEOUT_S = _env_float("THEYA_FETCH_TIMEOUT_S", 10.0)
MAX_BODY_BYTES = _env_int("THEYA_MAX_BODY_BYTES", 5 * 1024 * 1024)
MAX_REDIRECTS = _env_int("THEYA_MAX_REDIRECTS", 5)
ALLOWED_CONTENT_TYPES = ("text/html", "application/xhtml+xml", "text/plain")

# HTTP statuses where the site is probably blocking bots / needs JS, so the
# Jina fallback is worth a try. Other 4xx (404, 410...) are hard failures.
FALLBACK_STATUSES = frozenset({401, 403, 429, 503})

# --- Quality gate ------------------------------------------------------------
MIN_BODY_CHARS = _env_int("THEYA_MIN_BODY_CHARS", 500)
MIN_BODY_WORDS = _env_int("THEYA_MIN_BODY_WORDS", 100)
# If SPA-shell markers are present, require more words before trusting Tier 1.
SPA_SUSPECT_MIN_WORDS = _env_int("THEYA_SPA_SUSPECT_MIN_WORDS", 300)

# --- Audio Cache (Phase 3) ---------------------------------------------------
AUDIO_CACHE_MAX_ITEMS = _env_int("THEYA_AUDIO_CACHE_MAX_ITEMS", 500)
AUDIO_CACHE_MAX_BYTES = _env_int("THEYA_AUDIO_CACHE_MAX_BYTES", 256 * 1024 * 1024)  # 256 MB

# --- Jina Reader (Tier 2) ----------------------------------------------------
JINA_ENABLED = _env_bool("THEYA_JINA_ENABLED", True)
JINA_BASE_URL = os.getenv("THEYA_JINA_BASE_URL", "https://r.jina.ai/")
JINA_TIMEOUT_S = _env_float("THEYA_JINA_TIMEOUT_S", 25.0)
# Optional: a free Jina key raises the rate limit. Never required.
JINA_API_KEY = os.getenv("JINA_API_KEY")
# CSS selectors Jina should drop server-side before converting to Markdown.
JINA_REMOVE_SELECTORS = (
    "header, footer, nav, aside, form, "
    "[role=navigation], [role=banner], [role=contentinfo], "
    ".sidebar, .comments, #comments, .cookie, .newsletter"
)
