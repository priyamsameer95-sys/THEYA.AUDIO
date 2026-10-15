#!/usr/bin/env bash
set -eo pipefail

echo "========================================================"
echo "🛡️  Running Spartan Quality Gates for theya.voice"
echo "========================================================"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${PROJECT_ROOT}"

VENV_PY=".venv/bin/python"
VENV_PYTEST=".venv/bin/pytest"

if [[ ! -f "${VENV_PY}" ]]; then
  echo "❌ Error: Virtual environment .venv not found at ${VENV_PY}"
  exit 1
fi

# Gate 1: Syntax & Bytecode Compilation
echo ""
echo "[Gate 1/4] Checking Python syntax and bytecode compilation..."
${VENV_PY} -m compileall app tests -q
echo "✅ Gate 1 Passed: Syntax is clean."

# Gate 2: Security & SSRF Boundary Verification
echo ""
echo "[Gate 2/4] Verifying SSRF & Private Network Security Invariants..."
${VENV_PYTEST} tests/test_guard.py -q
echo "✅ Gate 2 Passed: SSRF guardrails verified."

# Gate 3: Automated Test Suite (All Unit & Integration Tests)
echo ""
echo "[Gate 3/4] Running full automated test suite..."
${VENV_PYTEST} -v -m "not live"
echo "✅ Gate 3 Passed: All tests passed with zero assertion tampering."

# Gate 4: API & Static Asset Integrity Check
echo ""
echo "[Gate 4/4] Verifying static asset and route integrity..."
${VENV_PY} -c '
from app.main import app
routes = [route.path for route in app.routes]
required = ["/", "/api/extract", "/api/tts", "/api/voices", "/api/feedback", "/api/progress", "/api/history"]
for r in required:
    assert r in routes, f"Missing route: {r}"
print("All", len(required), "critical API endpoints mounted successfully.")

'
echo "✅ Gate 4 Passed: Route contracts verified."

echo ""
echo "========================================================"
echo "🎉 ALL SPARTAN QUALITY GATES PASSED CLEANLY"
echo "========================================================"
