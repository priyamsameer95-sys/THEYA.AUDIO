---
name: spartan-quality-gates
description: Enforces strict sequential quality gates (Typecheck -> Lint -> Test -> Security -> Review) before code is accepted. Forbids patching tests to force passes.
---

# Spartan AI Quality Gates

Strict, automated sequence enforcement designed to prevent regressions, silent bugs, and artificial test patching.

## The Spartan Sequence
Before any feature or bugfix is marked complete, all stages must execute in strict linear order:

```
[1. Typecheck] ──► [2. Lint] ──► [3. Unit/Integration Tests] ──► [4. Security/Boundary Check] ──► [5. Review]
```

If any step fails, execution **must halt immediately**. You must address the root cause and restart from Step 1.

### Gate 1: Typecheck
- **TypeScript:** `tsc --noEmit` must exit with code 0.
- **Python:** `mypy` or `pyright` must verify types without untyped escapes.
- No `@ts-ignore`, `as any`, or `# type: ignore` workarounds unless strictly documented with an upstream library issue.

### Gate 2: Lint & Format
- Run the project's linter and formatter (`eslint`, `ruff`, `flake8`, `prettier`).
- Unused variables, unhandled promises, and syntax anti-patterns must be eliminated.

### Gate 3: Automated Tests
- Run the full test suite (`pytest`, `vitest`, `jest`).
- **Core Invariant:** Never modify test assertions or delete failing tests to claim completion. Tests define the contract; code must adapt to the contract.

### Gate 4: Security & Input Boundary Check
- Validate all network inputs with schema validators (Pydantic, Zod).
- Prevent SSRF: reject private/loopback/metadata addresses on outbound fetches.
- Prevent XSS: ensure user strings are sanitized before DOM injection.

### Gate 5: Review
- Perform an atomic diff inspection. Confirm only intended files were changed and no debugging artifacts (`console.log`, `print`) leaked into production code.
