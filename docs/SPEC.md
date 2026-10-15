# theya.voice: Behavioral & Architectural Specification

This specification defines the formal behavioral contracts, data models, error states, and security boundaries for **theya.voice**.

---

## 1. System Invariants

1. **Pure Single-Process Deployment:** The FastAPI ASGI application serves both JSON/Audio APIs and static assets on port `8000` with zero external database dependencies for local execution.
2. **Zero Plaintext SSRF Leaks:** Outbound network requests for user-submitted URLs must resolve hostnames and verify that every destination IP is a globally routable public address before sending HTTP bytes. Requests to loopback, link-local, carrier-grade NAT, private subnets, and cloud metadata (`169.254.169.254`) must be rejected with HTTP 400.
3. **Format Normalization:** All extraction tiers (Tier 0 Client HTML, Tier 1 Trafilatura, Tier 2 Jina Reader) must emit GitHub-Flavored Markdown so the downstream text sanitizer and pySBD segmenter can reliably identify headings, code blocks, and tables.
4. **Sentence Boundary Synchronization:** Every sentence unit maintains:
   - `idx`: Monotonically increasing zero-indexed integer.
   - `display_text`: The exact Markdown/prose text rendered in the Reader View.
   - `speech_text`: Cleaned pronounceable prose supplied to the TTS engine.
   - `kind`: Structural token (`title | heading | prose | code_cue | table_cue`).
5. **Deterministic Audio Cache & Dedup:** The audio cache key is `sha256(engine|voice|rate|speech_text)`. In-flight synthesis calls for the same key must share a single `asyncio.Future` to prevent duplicate network requests during lookahead prefetching.

---

## 2. API Contracts

### `POST /api/extract`
- **Request:**
  ```json
  {
    "url": "https://example.com/article",
    "html": null
  }
  ```
- **Response (200 OK):**
  ```json
  {
    "url": "https://example.com/article",
    "title": "Article Title",
    "author": "Author Name",
    "sitename": "example.com",
    "date": "2026-03-01",
    "extractor_used": "tier1-trafilatura",
    "word_count": 1420,
    "estimated_read_minutes": 8.1,
    "sentences": [
      {
        "idx": 0,
        "display_text": "Article Title",
        "speech_text": "Article Title.",
        "kind": "title"
      }
    ]
  }
  ```
- **Error Codes:**
  - `400 Bad Request`: Unsafe, malformed, or private/LAN URL.
  - `422 Unprocessable Entity`: No readable article prose could be extracted.
  - `502 Bad Gateway`: Upstream website timed out or disconnected.

### `GET /api/tts`
- **Query Parameters:**
  - `text` (required, 1–600 chars)
  - `voice` (optional, default `en-US-AndrewMultilingualNeural`)
  - `rate` (optional, default `+0%`)
  - `engine` (optional, default `edge`)
- **Response (200 OK):** `audio/mpeg` stream.
  - Headers: `X-Cache: HIT | MISS`, `Cache-Control: public, max-age=3600`.
- **Error Codes:**
  - `503 Service Unavailable`: Upstream TTS engine failure.

### `POST /api/feedback`
- **Request:**
  ```json
  {
    "rating": 5,
    "feedback_type": "general | extraction_issue | audio_quality | pronunciation",
    "article_url": "https://example.com/article",
    "sentence_idx": 12,
    "comments": "Optional feedback"
  }
  ```
- **Response (200 OK):**
  ```json
  {
    "status": "ok",
    "message": "Feedback received. Thank you!",
    "feedback": { ... }
  }
  ```

---

## 3. Discriminated UI State Machine Contract
The frontend client strictly models its lifecycle as a discriminated state union:

```
[IDLE]
  │
  ├──► [EXTRACTING { url }] ──(Error)──► [ERROR { message, url }]
  │
  ▼
[READY { article }]
  │
  ├──► [BUFFERING { article, index }]
  │       │
  │       ▼
  │     [PLAYING { article, index, generation }] ──► [PAUSED { article, index }]
  │       │
  │       ├──(Next sentence)──► [BUFFERING / PLAYING index + 1]
  │       └──(End of article)──► [FINISHED { article }]
```
