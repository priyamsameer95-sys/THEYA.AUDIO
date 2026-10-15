---
name: code-simplifier
description: Takes recently written or modified code and makes it cleaner, more explicit, and easier to maintain without changing what it does.
---

# Code Simplifier: Behavior-Preserving Refactoring

AI-generated code frequently works but accumulates cognitive overhead: deeply nested conditionals, multi-line nested ternaries, functions doing multiple unrelated things, and prematurely clever abstractions.

The Code Simplifier enforces one invariant: **Never change behavior; only refine how behavior is expressed.**

## Core Simplification Principles

### 1. Guard Clauses & Early Returns
Replace deeply nested `if/else` ladders with guard clauses that exit early:
```ts
// ❌ Nested complexity
function handleRequest(req) {
  if (req.user) {
    if (req.user.isActive) {
      if (req.data) {
        return process(req.data);
      } else {
        throw new Error("Missing data");
      }
    }
  }
}

// ✅ Explicit guard clauses
function handleRequest(req) {
  if (!req.user || !req.user.isActive) throw new Error("Unauthorized");
  if (!req.data) throw new Error("Missing data");
  return process(req.data);
}
```

### 2. Decompose Multi-purpose Functions
- If a function takes more than 3 parameters or spans more than 40 lines, look for cohesive sub-tasks that can be extracted into pure helper functions.

### 3. Eliminate Cryptic Syntax
- Replace multi-line nested ternary operators with explicit `if/else` or lookup tables / objects.
- Replace obscure regex or bitwise tricks with named helper functions explaining the intent.

### 4. Remove Dead Code & Redundant Checks
- Eliminate unreachable branches, unused parameters, commented-out dead code blocks, and obsolete TODO markers.
