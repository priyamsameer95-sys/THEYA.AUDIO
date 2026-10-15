# theya.voice — Operational Runbook & Developer Guide

This runbook contains operational workflows, troubleshooting runbooks, and developer instructions for running and maintaining **theya.voice**.

---

## 1. Quickstart & Local Development

### 1.1 Prerequisites
- Python 3.9+ (tested on Python 3.9.6 on macOS and Linux)
- Git and bash/zsh shell

### 1.2 Setup Environment
```bash
# Clone the repository
git clone https://github.com/your-org/theya.voice.git
cd theya.voice

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 1.3 Running the Development Server
```bash
# Start server with live reload enabled
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```
Navigate to `http://127.0.0.1:8000` in your web browser.

---

## 2. Quality Gates & Testing

`theya.voice` uses strict Spartan Quality Gates to prevent regression. Before submitting any changes or deploying, execute:

```bash
./scripts/quality_gate.sh
```

The script runs 4 sequential gates:
1. **Gate 1**: Python syntax and bytecode compilation (`compileall`).
2. **Gate 2**: SSRF security guard tests (`test_guard.py`).
3. **Gate 3**: Full automated test suite (85+ unit/integration tests).
4. **Gate 4**: Route contract verification (`/`, `/api/extract`, `/api/tts`, `/api/voices`, `/api/feedback`, `/api/progress`, `/api/history`).

### Running Specific Test Suites
```bash
# Run all offline unit & pipeline tests
.venv/bin/pytest -v -m "not live"

# Run live network integration tests (requires internet connection)
.venv/bin/pytest -v -m "live"

# Run specific test file
.venv/bin/pytest tests/test_db.py -v
```

---

## 3. Operational Endpoints & API Reference

| Endpoint | Method | Description |
| :--- | :--- | :--- |
| `/` | `GET` | Serves the single-page reader & lookahead audio player UI |
| `/api/extract` | `POST` | Two-tier extraction of clean Markdown + pySBD sentence breakdown |
| `/api/tts` | `GET` | Streams MP3 audio bytes for a single sentence (cached in RAM) |
| `/api/voices` | `GET` | Returns available high-naturalness neural voices grouped by language |
| `/api/progress` | `POST` | Upserts reading progress and calculates completion metrics |
| `/api/history` | `GET` | Retrieves recently read articles with progress percentages |
| `/api/feedback` | `POST` | Submits user feedback rating and optional commentary |
| `/api/feedback` | `GET` | Lists recent feedback submissions |

---

## 4. Production Deployment

### 4.1 Docker Container
Build and run the production container:
```bash
docker build -t theya-voice:latest .
docker run -d -p 8000:8000 --name theya-voice theya-voice:latest
```

### 4.2 Multi-Worker Production Server
```bash
.venv/bin/uvicorn app.main:app \
  --host 0.0.0.0 \
  --port 8000 \
  --workers 4 \
  --log-level info \
  --access-log
```

---

## 5. Troubleshooting Runbook

### Issue: "That link is private or cannot be reached safely" (HTTP 400)
- **Cause**: The submitted URL resolves to a loopback (`127.0.0.1`), private RFC 1918 IP, or metadata IP (`169.254.169.254`).
- **Remedy**: This is an intentional security boundary (SSRF protection). Ensure URLs point to publicly accessible internet domains.

### Issue: "Audio pause or gap between sentences"
- **Cause**: Lookahead prefetch is interrupted by slow network or rate limiting.
- **Remedy**: The browser automatically falls back to offline Web Speech synthesis if Edge-TTS fails. Check the Lookahead Buffer indicator in the bottom dock.

### Issue: "Database locked" in high concurrency
- **Cause**: SQLite opened in default DELETE journal mode.
- **Remedy**: `theya.voice` enforces WAL mode (`PRAGMA journal_mode = WAL;`) automatically on database initialization. Verify `data/theya.db` has corresponding `-wal` and `-shm` files during operation.
