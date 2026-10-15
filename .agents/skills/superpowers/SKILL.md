---
name: superpowers
description: Enforces the strict Clarify -> Spec -> Plan -> Execute -> Review engineering workflow with Test-Driven Development (TDD). Requires failing test before implementation.
---

# Superpowers Engineering Workflow & TDD

Superpowers forces a disciplined, five-stage engineering sequence for all non-trivial feature implementations and architectural modifications:

```
[1. Clarify] ──► [2. Spec] ──► [3. Plan & Review] ──► [4. Strict TDD] ──► [5. Verify & Review]
```

## Stage 1: Clarify
- Never start coding immediately upon receiving a vague or multi-faceted prompt.
- Explicitly identify ambiguities, implicit assumptions, edge cases, and constraints.
- Confirm target platforms, runtime versions, performance requirements, and scope boundaries.

## Stage 2: Spec (Behavioral Specification)
- Write down the precise behavioral contract:
  - Input shapes, types, and validation boundaries.
  - Success outputs and state transformations.
  - Explicit error conditions, HTTP status codes, or exception types.
- Ensure the user/stakeholder agrees with the spec before authoring plans.

## Stage 3: Plan-Eng-Review (Architecture & Data Flow)
- Lock in architecture and data flow before touching any application code.
- Produce a step-by-step implementation plan breaking the work into isolated, atomic milestones.
- Identify dependencies, data mutations, concurrency implications, and backwards compatibility.

## Stage 4: Strict Test-Driven Development (TDD)
- **The Red-Green-Refactor Invariant:**
  1. **Red:** Write a targeted, failing unit or integration test that asserts the specified behavior.
  2. **Verify Failure:** Run the test suite and confirm the test fails for the expected reason (not a syntax error or import error).
  3. **Green:** Write the minimal implementation required to make the failing test pass.
  4. **Verify Success:** Run the test suite and confirm all tests pass cleanly.
  5. **Refactor:** Clean up code, eliminate duplication, and verify tests remain green.
- **Strict Rule:** Never patch or weaken an assertion just to make a test pass. If a test fails unexpectedly, investigate the implementation or re-evaluate the spec.

## Stage 5: Final Review & Quality Signoff
- Review the diff for:
  - Unintended side effects or leaked abstractions.
  - Performance bottlenecks (e.g. unindexed queries, blocking I/O on async loops).
  - Code readability, test coverage, and documentation integrity.
